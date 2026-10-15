#!/usr/bin/env node
// Runs the real Claude Code twice per model against a stand-in Messages API: once as shipped and once
// with lean-harness seated by policy the way templates/40-claude-lean-harness.json.j2 seats it, next
// to the skillOverrides of templates/10-claude-personal.json.j2. What the two requests differ in must
// be exactly what is meant to change: the tools the mod defers, the lines and sections it drops, the
// agent it hides, the skill entries the overrides take out. Everything else, the stand-ins for things
// added on a machine above all (tests/live/userkit, a skill and an agent in the home folder), must
// come through byte for byte. It also fails when a target is gone from Claude Code, which is how a new
// version announces a rule to update.
//
// No account and no network: the API key is fake and every request goes to the stand-in. Policy
// lives in /etc/claude-code only, so each run gets its own folder there: bind-mounted in a user and
// mount namespace (unshare, no root), or with sudo where namespaces are off (CI runners only).
//
//   node check.mjs [--claude PATH] [--seat auto|unshare|sudo] [--models a,b] [--keep]

import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import * as mod from '../../hooks/register.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PLUGIN = path.resolve(HERE, '../..')
const MODS = path.resolve(PLUGIN, '../..')
const ANSIBLE = path.resolve(MODS, '../../..')
const TEMPLATES = path.join(ANSIBLE, 'templates')
const PROBE = path.join(HERE, 'probe')
const USERKIT = path.join(HERE, 'userkit')
const MOD_ID = 'lean-harness@computerconfiguration'

// Under `claude -p` with an API key Claude Code doesn't offer these, so their rules can't be seen
// here; the fixtures captured from a logged-in session (tests/fixtures) cover them.
const NOT_OFFERED_HEADLESS = { tools: ['SendFeedback'], lines: ['ultrareview'] }

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]?.startsWith('--') || all[i + 1] === undefined ? true : all[i + 1]]] : acc), []),
)
const MODELS = (args.models ?? 'claude-haiku-5-5,claude-opus-5-5,claude-sonnet-5-5,claude-fable-5-1').split(',')

// ── report ───────────────────────────────────────────────────────────────────────
let failures = 0
const ok = (msg) => console.log(`ok    ${msg}`)
const fail = (msg) => {
  failures++
  console.log(`FAIL  ${msg}`)
}
const note = (msg) => console.log(`note  ${msg}`)
const check = (cond, msg, detail) => (cond ? ok(msg) : fail(detail ? `${msg}\n      ${detail}` : msg))

function firstDifference(a, b) {
  let i = 0
  while (i < a.length && i < b.length && a[i] === b[i]) i++
  return `at ${i}: expected ${JSON.stringify(a.slice(Math.max(0, i - 80), i + 120))}\n      got      ${JSON.stringify(b.slice(Math.max(0, i - 80), i + 120))}`
}

// A listing entry's name: `- name: description`, `- plugin:name: …`, or a bare `- name`.
const entryName = (line) => /^- ((?:[\w.-]+:)?[\w.-]+)(?=: |:$|$)/.exec(line)?.[1] ?? null

// ── templates ────────────────────────────────────────────────────────────────────
// The playbook's Jinja2 here is comments and plain {{ var }}: enough to render and parse.
function render(file, vars) {
  const text = fs.readFileSync(file, 'utf8').replace(/\{#[\s\S]*?#\}/g, '')
  if (/\{%/.test(text)) throw new Error(`${file}: template logic this check can't render`)
  return JSON.parse(
    text.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, name) => {
      if (!(name in vars)) throw new Error(`${file}: no test value for ${name}`)
      return vars[name]
    }),
  )
}

const VARS = { user_home: '/home/test', claude_otel_endpoint: 'https://otel.example/v1/metrics', claude_otel_host: 'test', claude_mods_dir: MODS }
const policy = {}
for (const file of fs.readdirSync(TEMPLATES).filter((f) => /claude.*\.json\.j2$/.test(f))) {
  try {
    policy[file] = render(path.join(TEMPLATES, file), VARS)
    ok(`template ${file} renders to JSON`)
  } catch (err) {
    fail(`template ${file}: ${err.message}`)
  }
}
const seat = policy['40-claude-lean-harness.json.j2']
const personal = policy['10-claude-personal.json.j2']
const overrides = personal?.skillOverrides ?? {}
// What Claude Code does without the overrides: the shipped run gets the personal drop-in minus them.
const { skillOverrides: _, ...personalShipped } = personal ?? {}
check(
  seat?.prependPlugins?.[0] === MOD_ID && seat.prependPlugins.includes('sec-default@builtin') && seat.enabledPlugins?.[MOD_ID] === true,
  'the lean-harness drop-in seats the mod first and keeps sec-default',
)
check(seat?.extraKnownMarketplaces?.computerconfiguration?.source?.path === MODS, 'the drop-in points the marketplace at the mods folder')
check(
  JSON.stringify(personal?.deniedMcpServers) === JSON.stringify([{ serverName: 'claude.ai Claude Docs' }]),
  'the personal drop-in denies exactly the Claude Docs connector',
)

// ── skill overrides against the newest capture ───────────────────────────────────
// Headless, without an account, Claude Code lists only its built-in skills; the fixture captured from
// a logged-in session has the claude.ai ones too. Every override must still name a listed skill.
const CLAUDE_AI = 'anthropic-skills:'
const MODES = ['on', 'name-only', 'user-invocable-only', 'off']
const FIXTURES = path.join(PLUGIN, 'tests/fixtures')
const newest = fs
  .readdirSync(FIXTURES)
  .filter((f) => /^v[\d.]+\.ts$/.test(f))
  .sort((a, b) => a.match(/\d+/g).map(Number).reduce((r, n, i) => r || n - b.match(/\d+/g).map(Number)[i], 0))
  .pop()
const fixtureText = fs.readFileSync(path.join(FIXTURES, newest), 'utf8')
const fixture = JSON.parse(fixtureText.slice(fixtureText.indexOf('{')))
const fixtureNames = fixture.attachments.skill_listing.split('\n').map((l) => entryName(l)).filter(Boolean)
check(Object.keys(overrides).length > 0, 'the personal drop-in sets skillOverrides')
for (const [name, mode] of Object.entries(overrides)) {
  const listed = fixtureNames.includes(name) || fixtureNames.includes(CLAUDE_AI + name)
  check(MODES.includes(mode) && listed, `skillOverrides.${name} (${mode}) names a skill ${fixture.version} lists`, MODES.includes(mode) ? 'not in the captured listing' : `unknown mode ${mode}`)
}

// ── Claude Code ──────────────────────────────────────────────────────────────────
function which(cmd) {
  const r = spawnSync('sh', ['-c', `command -v ${cmd}`], { encoding: 'utf8' })
  return r.status === 0 ? r.stdout.trim() : null
}
const CLAUDE = typeof args.claude === 'string' ? path.resolve(args.claude) : which('claude')
if (!CLAUDE) {
  fail('no claude on PATH (or pass --claude)')
  process.exit(1)
}
const version = spawnSync(CLAUDE, ['--version'], { encoding: 'utf8' }).stdout.trim()
note(`Claude Code ${version} (${CLAUDE})`)

function chooseSeat() {
  const want = args.seat ?? 'auto'
  const etcExists = fs.existsSync('/etc/claude-code')
  const unshareWorks = etcExists && spawnSync('unshare', ['--user', '--map-root-user', '--mount', 'true']).status === 0
  if (want === 'unshare' || (want === 'auto' && unshareWorks)) {
    if (!unshareWorks) throw new Error('unshare: no user namespaces here, or no /etc/claude-code to mount over')
    return 'unshare'
  }
  // sudo bind-mounts over the real /etc/claude-code for each run; only where nothing lives there.
  if (!process.env.CI) throw new Error('no user namespaces here; the sudo seat runs only under CI=true')
  if (spawnSync('sudo', ['-n', 'true']).status !== 0) throw new Error('neither unshare nor passwordless sudo works here')
  spawnSync('sudo', ['-n', 'mkdir', '-p', '/etc/claude-code'])
  return 'sudo'
}
let SEAT
try {
  SEAT = chooseSeat()
  note(`policy seat: ${SEAT}`)
} catch (err) {
  fail(err.message)
  process.exit(1)
}

// ── the stand-in API ─────────────────────────────────────────────────────────────
let current = null
const server = http.createServer((req, res) => {
  let body = ''
  req.on('data', (c) => (body += c))
  req.on('end', () => {
    if (req.method === 'POST' && /^\/v1\/messages(\?|$)/.test(req.url)) {
      const parsed = JSON.parse(body || '{}')
      current?.push(parsed)
      const model = parsed.model ?? 'claude-haiku-5-5'
      const message = { id: 'msg_check', type: 'message', role: 'assistant', model, content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 1, output_tokens: 1 } }
      if (!parsed.stream) {
        res.writeHead(200, { 'content-type': 'application/json' })
        return res.end(JSON.stringify({ ...message, content: [{ type: 'text', text: 'ok' }], stop_reason: 'end_turn' }))
      }
      res.writeHead(200, { 'content-type': 'text/event-stream' })
      const ev = (type, data) => res.write(`event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`)
      ev('message_start', { message })
      ev('content_block_start', { index: 0, content_block: { type: 'text', text: '' } })
      ev('content_block_delta', { index: 0, delta: { type: 'text_delta', text: 'ok' } })
      ev('content_block_stop', { index: 0 })
      ev('message_delta', { delta: { stop_reason: 'end_turn', stop_sequence: null }, usage: { output_tokens: 1 } })
      ev('message_stop', {})
      return res.end()
    }
    if (req.url.includes('count_tokens')) {
      res.writeHead(200, { 'content-type': 'application/json' })
      return res.end(JSON.stringify({ input_tokens: 1 }))
    }
    res.writeHead(404, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ type: 'error', error: { type: 'not_found_error', message: 'stand-in API' } }))
  })
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const BASE_URL = `http://127.0.0.1:${server.address().port}`

// ── one run ──────────────────────────────────────────────────────────────────────
const WORK = fs.mkdtempSync(path.join(os.tmpdir(), 'lh-check-'))

function writeFile(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, text)
}

// Things a person adds in their home folder.
function plantHome(home, { agent }) {
  writeFile(path.join(home, '.claude/skills/my-notes/SKILL.md'), '---\nname: my-notes\ndescription: HOME-MARKER a skill of my own. Use when the user says the word notes-fig.\n---\n\nSay "fig".\n')
  if (agent) writeFile(path.join(home, '.claude/agents/statusline-setup.md'), '---\nname: statusline-setup\ndescription: HOME-MARKER an agent of my own named like the built-in statusline-setup agent.\n---\n\nReply "ok".\n')
}

function managedDir(name, withMod) {
  const dir = path.join(WORK, name, 'etc-claude-code')
  writeFile(path.join(dir, 'managed-settings.d/10-claude-personal.json'), JSON.stringify(withMod ? personal : personalShipped, null, 2))
  if (withMod) writeFile(path.join(dir, 'managed-settings.d/40-claude-lean-harness.json'), JSON.stringify(seat, null, 2))
  return dir
}

// spawnSync would block the stand-in API, which lives on this process's event loop.
function exec(cmd, argv, opts) {
  return new Promise((resolve) => {
    const child = spawn(cmd, argv, { ...opts, stdio: ['ignore', 'pipe', 'pipe'] })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (d) => (stdout += d))
    child.stderr.on('data', (d) => (stderr += d))
    const timer = setTimeout(() => child.kill('SIGKILL'), 180_000)
    child.on('close', (status) => {
      clearTimeout(timer)
      resolve({ status, stdout, stderr })
    })
  })
}

async function run(name, { model, withMod, agent = false }) {
  const root = path.join(WORK, name)
  // One home path for every run: it shows up in the prompt (memory folder, working directory).
  const home = path.join(WORK, 'home')
  fs.rmSync(home, { recursive: true, force: true })
  const probeOut = path.join(root, 'probe')
  fs.mkdirSync(path.join(home, 'project'), { recursive: true })
  fs.mkdirSync(probeOut, { recursive: true })
  plantHome(home, { agent })
  const etc = managedDir(name, withMod)
  const debug = path.join(root, 'debug.log')
  const argv = [CLAUDE, '-p', '--model', model, '--plugin-dir', PROBE, '--plugin-dir', USERKIT, '--debug-file', debug, 'hi']
  const env = {
    PATH: [path.dirname(CLAUDE), path.dirname(process.execPath), '/usr/local/bin', '/usr/bin', '/bin'].join(':'),
    HOME: home,
    TERM: 'dumb',
    ANTHROPIC_BASE_URL: BASE_URL,
    ANTHROPIC_API_KEY: 'sk-ant-api03-check-0000000000000000000000000000000000000000',
    // A gateway turns tool search off; the real thing has it on, and deferral needs it.
    ENABLE_TOOL_SEARCH: 'true',
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1',
    DISABLE_AUTOUPDATER: '1',
    PROBE_OUT: probeOut,
  }
  current = []
  const cwd = path.join(home, 'project')
  let r
  if (SEAT === 'unshare') {
    r = await exec('unshare', ['--user', '--map-root-user', '--mount', 'sh', '-c', 'mount --rbind "$1" /etc/claude-code && shift && exec "$@"', 'sh', etc, ...argv], { cwd, env })
  } else {
    spawnSync('sudo', ['-n', 'mount', '--bind', etc, '/etc/claude-code'])
    try {
      r = await exec(argv[0], argv.slice(1), { cwd, env })
    } finally {
      spawnSync('sudo', ['-n', 'umount', '/etc/claude-code'])
    }
  }
  const requests = current
  current = null
  const main = requests.filter((q) => Array.isArray(q.tools)).sort((a, b) => b.tools.length - a.tools.length)[0]
  const read = (f) => (fs.existsSync(path.join(probeOut, f)) ? JSON.parse(fs.readFileSync(path.join(probeOut, f), 'utf8')) : null)
  return { name, status: r.status, stdout: r.stdout, stderr: r.stderr, debug: fs.existsSync(debug) ? fs.readFileSync(debug, 'utf8') : '', main, probe: read('session.json') }
}

// ── reading a request ────────────────────────────────────────────────────────────
const upFront = (q) => q.tools.filter((t) => t.name && !t.defer_loading).map((t) => t.name)
const systemText = (q) =>
  q.system
    .map((b) => b.text ?? '')
    .filter((t) => !t.startsWith('x-anthropic-billing-header'))
    .join('\n\n')
const messageText = (q) =>
  q.messages
    .flatMap((m) => (Array.isArray(m.content) ? m.content : [{ type: 'text', text: m.content }]))
    .filter((c) => c.type === 'text')
    .map((c) => c.text)
    .join('\n\n')

// A listing: its header line, a blank line, entries up to the next blank line.
function listing(text, header) {
  const at = text.indexOf(header)
  if (at < 0) return null
  const body = text.slice(at + header.length).replace(/^\n\n?/, '')
  const end = body.indexOf('\n\n')
  return (end < 0 ? body : body.slice(0, end)).replace(/\n<\/system-reminder>[\s\S]*$/, '').split('\n')
}
const SKILLS_HEADER = 'The following skills are available for use with the Skill tool:'
const AGENTS_HEADER = 'Available agent types for the Agent tool:'
const DEFERRED_HEADER = 'The following deferred tools are now available via ToolSearch.'

// Entries as [name, lines], a description's later lines kept with it.
function entries(lines) {
  const out = []
  for (const line of lines ?? []) {
    if (line.startsWith('- ') || out.length === 0) out.push([entryName(line), [line]])
    else out[out.length - 1][1].push(line)
  }
  return out
}

// ── the comparison ───────────────────────────────────────────────────────────────
function compare(model, raw, lean) {
  const tag = `${model}:`
  check(raw.main && lean.main, `${tag} both runs reached the stand-in API`, `raw ${raw.status} ${raw.stderr.slice(0, 300)} | lean ${lean.status} ${lean.stderr.slice(0, 300)}`)
  if (!raw.main || !lean.main) return
  check(/hooks module lean-harness@computerconfiguration loaded \([^)]*tier prepend\)/.test(lean.debug), `${tag} policy seats lean-harness in the prepend tier`)
  check(!/hooks module lean-harness@/.test(raw.debug), `${tag} the run as shipped has no lean-harness`)
  const trouble = lean.debug.split('\n').filter((l) => /(^|\s)(lean-harness: |hooks module lean-harness@)/.test(l) && /threw|refused|skipped|did not load|failed/i.test(l))
  check(trouble.length === 0, `${tag} no lean-harness hook threw, failed or was refused`, trouble.slice(0, 3).join('\n      '))

  // Tools: the deferred ones leave the up-front list, nothing else moves.
  const rawTools = upFront(raw.main)
  const leanTools = upFront(lean.main)
  check(rawTools.includes('ToolSearch'), `${tag} tool search is on, so deferral is observable`)
  const offered = mod.DEFER.filter((t) => rawTools.includes(t))
  const gone = mod.DEFER.filter((t) => !rawTools.includes(t) && !NOT_OFFERED_HEADLESS.tools.includes(t))
  check(gone.length === 0, `${tag} every tool the mod defers is still a tool Claude Code offers up front`, `no longer offered: ${gone.join(', ')}`)
  const expectTools = rawTools.filter((t) => !offered.includes(t))
  check(JSON.stringify(leanTools) === JSON.stringify(expectTools), `${tag} up-front tools are the shipped ones minus ${offered.join(', ')}`, `expected ${expectTools.join(',')} got ${leanTools.join(',')}`)

  // System prompt: shipped text minus exactly what the rules drop, the deferred line in place of
  // the idle budget line.
  const sections = raw.probe?.compose?.[model]
  check(Array.isArray(sections), `${tag} the probe read the composed sections`)
  if (Array.isArray(sections)) {
    let expected = systemText(raw.main)
    const identity = sections.filter((s) => !s.id.includes(':') && mod.DROP_SECTIONS.some((r) => r.match(s.id)))
    if (model.includes('fable')) check(identity.length > 0, `${tag} Fable still has the identity section the mod drops`, `ids: ${sections.map((s) => s.id).join(', ')}`)
    for (const s of identity) expected = expected.replace(`\n\n${s.text}`, '')
    for (const rule of mod.DROP_LINES) {
      const lines = sections.filter((s) => rule.section(s.id)).flatMap((s) => s.text.split('\n').filter((l) => l.startsWith(rule.opening)))
      if (lines.length === 0) {
        if (NOT_OFFERED_HEADLESS.lines.some((w) => rule.opening.includes(w))) note(`${tag} "${rule.opening.trim()}" isn't in a headless prompt; the fixtures cover it`)
        else fail(`${tag} no line opens with "${rule.opening.trim()}" any more: Claude Code reworded or moved it`)
      }
      for (const line of lines) expected = expected.replace(`\n${line}`, '')
    }
    const budget = sections.find((s) => s.id === 'total_tokens')
    check(budget && mod.isIdleBudget(budget.text), `${tag} the idle budget line is still there to drop`, budget ? JSON.stringify(budget.text) : 'no total_tokens section')
    const line = offered.length > 0 ? mod.deferredLine(offered) : null
    if (budget) expected = expected.replace(budget.text, line ?? '').replace(/\n\n\n\n/, '\n\n')
    const got = systemText(lean.main)
    check(got === expected, `${tag} the system prompt differs from the shipped one by exactly the rules`, firstDifference(expected, got))
  }

  // Skill listing: the overridden built-ins go, the stand-ins stay, the rest is untouched. claude.ai
  // skills aren't listed without an account; the fixture check above covers their names.
  const rawSkills = entries(listing(messageText(raw.main), SKILLS_HEADER))
  const leanSkills = entries(listing(messageText(lean.main), SKILLS_HEADER))
  check(rawSkills.length > 0, `${tag} the shipped request lists skills`)
  const marked = (e) => e[1].join('\n').includes('MARKER')
  const mine = rawSkills.filter(marked)
  check(mine.length === 3, `${tag} the planted skills are listed`, `found ${mine.map((e) => e[0]).join(', ')}`)
  const builtins = Object.keys(overrides).filter((n) => !fixtureNames.includes(CLAUDE_AI + n))
  const missing = builtins.filter((n) => !rawSkills.some((e) => e[0] === n))
  check(missing.length === 0, `${tag} every built-in skill with an override is still listed`, `not listed: ${missing.join(', ')}`)
  const expectSkills = rawSkills.flatMap((e) => {
    const mode = overrides[e[0]] ?? 'on'
    if (mode === 'off' || mode === 'user-invocable-only') return []
    return [mode === 'name-only' ? `- ${e[0]}` : e[1].join('\n')]
  })
  const gotSkills = leanSkills.map((e) => e[1].join('\n'))
  check(JSON.stringify(gotSkills) === JSON.stringify(expectSkills), `${tag} the skill listing changes by exactly the overrides`, firstDifference(expectSkills.join('\n'), gotSkills.join('\n')))
  for (const e of mine) check(gotSkills.includes(e[1].join('\n')), `${tag} ${e[0]} (added on the machine) is listed unchanged`)

  // Agent listing: the built-in statusline-setup goes, the rest is untouched.
  const rawAgents = entries(listing(messageText(raw.main), AGENTS_HEADER))
  const leanAgents = entries(listing(messageText(lean.main), AGENTS_HEADER))
  const hidden = rawAgents.filter((e) => mod.HIDDEN_AGENTS.includes(e[0]) && !marked(e))
  check(hidden.length === mod.HIDDEN_AGENTS.length, `${tag} the built-in agents the mod hides are still offered`, `listed: ${rawAgents.map((e) => e[0]).join(', ')}`)
  const expectAgents = rawAgents.filter((e) => !hidden.includes(e)).map((e) => e[1].join('\n'))
  check(JSON.stringify(leanAgents.map((e) => e[1].join('\n'))) === JSON.stringify(expectAgents), `${tag} the agent listing loses ${hidden.map((e) => e[0]).join(', ')} and nothing else`)
  for (const e of rawAgents.filter(marked)) check(leanAgents.some((l) => l[1].join('\n') === e[1].join('\n')), `${tag} agent ${e[0]} (added on the machine) is offered unchanged`)

  // The stand-in MCP server's tool, named like a deferred built-in, stays where Claude Code put it.
  const mcpWhere = (q) => {
    const up = upFront(q).filter((n) => n.startsWith('mcp__') && n.endsWith('__ScheduleWakeup'))
    const deferred = (listing(messageText(q), DEFERRED_HEADER) ?? []).filter((l) => /^mcp__.*__ScheduleWakeup$/.test(l))
    return JSON.stringify({ up, deferred })
  }
  check(mcpWhere(raw.main) !== JSON.stringify({ up: [], deferred: [] }), `${tag} the stand-in MCP server's ScheduleWakeup tool is offered`)
  check(mcpWhere(lean.main) === mcpWhere(raw.main), `${tag} the MCP tool named ScheduleWakeup is left where Claude Code put it`)

  // The per-request budget reminder.
  const rawBudget = (messageText(raw.main).match(/<total_tokens>\d+ tokens left<\/total_tokens>/g) ?? []).length
  const leanBudget = (messageText(lean.main).match(/<total_tokens>\d+ tokens left<\/total_tokens>/g) ?? []).length
  if (rawBudget === 0) note(`${tag} no budget reminder in a first headless request`)
  else check(leanBudget === 0, `${tag} the idle budget reminder is dropped`)
}

// A home-folder agent named like the hidden built-in replaces it, and must then be left alone.
function compareOwnAgent(model, raw, lean) {
  const tag = `${model} (own statusline-setup agent):`
  if (!raw.main || !lean.main) return fail(`${tag} a run didn't reach the stand-in API`)
  const own = (q) => entries(listing(messageText(q), AGENTS_HEADER)).find((e) => e[0] === 'statusline-setup' && e[1].join('\n').includes('HOME-MARKER'))
  check(own(raw.main), `${tag} it is listed as shipped`)
  check(own(lean.main) && own(lean.main)[1].join('\n') === own(raw.main)[1].join('\n'), `${tag} lean-harness leaves it listed unchanged`)
}

// ── the runs ─────────────────────────────────────────────────────────────────────
try {
  for (const model of MODELS) {
    const short = model.replace(/^claude-/, '')
    compare(model, await run(`${short}-shipped`, { model, withMod: false }), await run(`${short}-lean`, { model, withMod: true }))
  }
  const model = MODELS[0]
  compareOwnAgent(model, await run('own-agent-shipped', { model, withMod: false, agent: true }), await run('own-agent-lean', { model, withMod: true, agent: true }))
} finally {
  server.close()
  if (args.keep) note(`runs kept in ${WORK}`)
  else fs.rmSync(WORK, { recursive: true, force: true })
}

console.log(failures === 0 ? '\nall checks passed' : `\n${failures} check(s) failed`)
process.exit(failures === 0 ? 0 : 1)
