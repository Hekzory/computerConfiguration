// lean-harness's unit tests: `claude plugin test` in this folder. The fixtures are what a logged-in
// Claude Code composed, offered and listed, one file per version (tests/live/capture.py writes them).
// Every fixture must come out trimmed exactly as meant with nothing else touched; the newest one must
// still hold a target for every rule. tests/live/check.mjs runs the real Claude Code on top of this,
// and checks the skillOverrides of templates/10-claude-personal.json.j2 against the newest fixture.

import { expect, test } from 'claude-code/testing'
import {
  BUDGET_FLOOR,
  DEFER,
  DEFERRED_ID,
  DROP_LINES,
  DROP_SECTIONS,
  HIDDEN_AGENTS,
  deferredLine,
  isIdleBudget,
  trimSections,
} from '../hooks/register.js'
import { FIXTURES, LATEST } from './fixtures/index.ts'

const ENGINE = { plugin: 'engine', tier: 'core' }
const openings = DROP_LINES.map((r) => r.opening)

// ── every captured version, every model ──────────────────────────────────────────

for (const fx of FIXTURES as any[]) {
  for (const [model, sections] of Object.entries(fx.sections) as [string, any[]][]) {
    test(`${fx.version} ${model}: rules drop what they name and leave the rest byte for byte`, () => {
      const out = trimSections(sections, fx.requestTools)
      const dropped = (s: any) => DROP_SECTIONS.some((r) => r.match(s.id)) || (s.id === 'total_tokens' && isIdleBudget(s.text))
      const kept = sections.filter((s) => !dropped(s))
      expect(out.map((s: any) => s.id)).toEqual([...kept.map((s) => s.id), DEFERRED_ID])
      for (const [i, s] of kept.entries()) {
        const rules = DROP_LINES.filter((r) => r.section(s.id))
        const lines = s.text.split('\n')
        const expected = rules.length === 0 ? s.text : lines.filter((l: string) => !rules.some((r) => l.startsWith(r.opening))).join('\n')
        expect(out[i]).toEqual({ ...s, text: expected })
      }
      for (const s of out) for (const line of s.text.split('\n')) expect(openings.some((o) => line.startsWith(o))).toBe(false)
      expect(out[out.length - 1]).toEqual({ id: DEFERRED_ID, scope: 'session', text: deferredLine(DEFER.filter((t) => fx.requestTools.includes(t))) })
    })
  }
}

// ── the newest version still has a target for every rule ─────────────────────────
// A failure here means Claude Code renamed, reworded or dropped what a rule names: update the rule
// (or drop it) in hooks/register.js.

const fx = LATEST as any
const allSections = Object.values(fx.sections).flat() as any[]

test(`${fx.version}: every line rule finds its line`, () => {
  for (const rule of DROP_LINES) {
    const hits = allSections.filter((s) => rule.section(s.id)).flatMap((s) => s.text.split('\n').filter((l: string) => l.startsWith(rule.opening)))
    expect({ rule: rule.opening, hits: hits.length > 0 }).toEqual({ rule: rule.opening, hits: true })
  }
})

test(`${fx.version}: every section rule finds its section, Fable's identity among them`, () => {
  for (const rule of DROP_SECTIONS) expect({ rule: rule.why, hit: allSections.some((s) => rule.match(s.id)) }).toEqual({ rule: rule.why, hit: true })
  expect(fx.sections['claude-fable-5-1'].some((s: any) => s.id === 'fable_identity')).toBe(true)
})

test(`${fx.version}: every model carries the idle budget line, and the reminder is idle too`, () => {
  for (const [model, sections] of Object.entries(fx.sections) as [string, any[]][]) {
    expect({ model, idle: sections.some((s) => s.id === 'total_tokens' && isIdleBudget(s.text)) }).toEqual({ model, idle: true })
  }
  expect(isIdleBudget(fx.attachments.total_tokens_reminder)).toBe(true)
})

test(`${fx.version}: every deferred tool is a built-in Claude Code lists up front`, () => {
  for (const tool of DEFER) expect({ tool, ...fx.tools[tool] }).toMatchObject({ tool, provider: ENGINE, isDeferred: false })
  expect(fx.requestTools).toContain('ToolSearch')
})

test(`${fx.version}: every hidden agent is a built-in Claude Code offers`, () => {
  for (const agent of HIDDEN_AGENTS) expect({ agent, ...fx.agents[agent] }).toMatchObject({ agent, source: 'built-in', provider: ENGINE, offered: true })
})

// ── sections ─────────────────────────────────────────────────────────────────────

const WITH_SEARCH = ['Bash', 'ToolSearch', ...DEFER]

test("a plugin's sections are never touched, whatever they hold", () => {
  const sections = [
    { id: 'acme:fable_identity', scope: 'session', text: 'This iteration of Claude is mine.' },
    { id: 'acme:env_info', scope: 'session', text: '# Mine\n - Claude Code is available as a CLI\n - Fast mode for Claude Code is mine' },
    { id: 'acme:total_tokens', scope: 'session', text: '<total_tokens>15000000 tokens left</total_tokens>' },
    { id: 'acme:session_guidance', scope: 'session', text: ' - If the user asks about "ultrareview", mine' },
  ]
  expect(trimSections(sections, []).map((s: any) => s.text)).toEqual(sections.map((s) => s.text))
})

test('sections Claude Code adds later come through as shipped', () => {
  const sections = [{ id: 'brand_new', scope: 'session', text: '# New\n - Claude Code is available as a toaster' }]
  expect(trimSections(sections, [])).toEqual(sections)
})

test('a reworded target line is kept as shipped', () => {
  const sections = [
    { id: 'session_guidance', scope: 'session', text: '# Session-specific guidance\n - Asked about ultrareview? Explain it.' },
    { id: 'env_info_v9', scope: 'session', text: '# Environment\n - Claude Code runs in many places.\n - Fast mode exists.' },
  ]
  expect(trimSections(sections, [])).toEqual(sections)
})

test('a real token budget stays, an idle one goes', () => {
  const at = (n: number) => [{ id: 'total_tokens', scope: 'session', text: `<total_tokens>${n} tokens left</total_tokens>` }]
  expect(trimSections(at(BUDGET_FLOOR - 1), [])).toEqual(at(BUDGET_FLOOR - 1))
  expect(trimSections(at(BUDGET_FLOOR), [])).toEqual([])
  expect(trimSections(at(14_851_110), [])).toEqual([])
  const odd = [{ id: 'total_tokens', scope: 'session', text: '<total_tokens>lots left</total_tokens>' }]
  expect(trimSections(odd, [])).toEqual(odd)
})

test('the deferred line names only what is offered, needs ToolSearch and comes once', () => {
  const base = [{ id: 'pronouns', scope: 'session', text: 'x' }]
  expect(trimSections(base, ['Bash', 'ScheduleWakeup'])).toEqual(base)
  expect(trimSections(base, ['Bash', 'ToolSearch'])).toEqual(base)
  const out = trimSections(base, ['ToolSearch', 'ReportFindings', 'Workflow', 'ScheduleWakeup'])
  expect(out[out.length - 1]).toEqual({ id: DEFERRED_ID, scope: 'session', text: deferredLine(['ScheduleWakeup', 'ReportFindings']) })
  expect(trimSections(out, ['ToolSearch', 'ScheduleWakeup']).filter((s: any) => s.id === DEFERRED_ID)).toHaveLength(1)
})

// ── the hooks, wired through Claude Code's own test harness ──────────────────────

test('compose: the hook trims with the tools the request offers', async ($, on) => {
  on('prompt.compose', () => ({ sections: fx.sections['claude-fable-5-1'] }))
  const r = await $.prompt.compose({ model: 'claude-fable-5-1', promptModel: 'claude-fable-5-1', surfaces: ['terminal'], tools: fx.requestTools, outputStyle: null, traits: ['lean'] })
  expect(r.sections).toEqual(trimSections(fx.sections['claude-fable-5-1'], fx.requestTools))
  expect(r.sections.some((s: any) => s.id === 'fable_identity' || s.id === 'total_tokens')).toBe(false)
})

test('attachments: the idle reminder goes, a real one and every other kind stay', async ($, on) => {
  on('prompt.attachment', ($: any, e: any) => ({ text: e.text }))
  const attach = (type: string, text: string) => $.prompt.attachment({ type, text, origin: { kind: 'engine' } })
  expect((await attach('total_tokens_reminder', fx.attachments.total_tokens_reminder)).text).toBe(null)
  expect((await attach('total_tokens_reminder', '<total_tokens>90000 tokens left</total_tokens>')).text).toBe('<total_tokens>90000 tokens left</total_tokens>')
  for (const type of ['skill_listing', 'agent_listing_delta', 'deferred_tools_delta', 'mcp_instructions_delta']) {
    if (fx.attachments[type]) expect((await attach(type, fx.attachments[type])).text).toBe(fx.attachments[type])
  }
})

test('tools: only the named built-ins wait; MCP, plugin and every other tool keep their place', async ($, on) => {
  on('tool.describe', ($: any, e: any) => ({ description: e.description, ...(e.isDeferred ? { isDeferred: true } : {}) }))
  for (const [tool, t] of Object.entries(fx.tools) as [string, any][]) {
    const r = await $.tool.describe({ tool, description: 'd', provider: t.provider, ...(t.isDeferred ? { isDeferred: true } : {}) })
    const deferred = DEFER.includes(tool) && t.provider.plugin === 'engine' ? true : t.isDeferred
    expect({ tool, deferred: r.isDeferred === true, description: r.description }).toEqual({ tool, deferred, description: 'd' })
  }
  const mine = await $.tool.describe({ tool: 'ScheduleWakeup', description: 'mine', provider: { plugin: 'acme', tier: 'user' } })
  expect(mine).toEqual({ description: 'mine' })
})

test('agents: only the built-in statusline-setup is hidden; yours and every other stay', async ($, on) => {
  on('agent.offer', () => ({ isOffered: true }))
  for (const [agent, a] of Object.entries(fx.agents) as [string, any][]) {
    const r = await $.agent.offer({ agent, description: a.description, source: a.source, provider: a.provider })
    expect({ agent, offered: r.isOffered }).toEqual({ agent, offered: !HIDDEN_AGENTS.includes(agent) })
  }
  const mine = await $.agent.offer({ agent: 'statusline-setup', description: 'mine', source: 'userSettings', provider: { plugin: 'user', tier: 'user' } })
  expect(mine.isOffered).toBe(true)
  const plugin = await $.agent.offer({ agent: 'statusline-setup', description: 'theirs', source: 'plugin', provider: { plugin: 'acme', tier: 'user' } })
  expect(plugin.isOffered).toBe(true)
})
