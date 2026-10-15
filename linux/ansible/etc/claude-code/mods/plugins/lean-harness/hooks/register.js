// lean-harness: trims what every Claude Code request carries. Each request re-reads the whole
// prefix (tools, system prompt, skill and agent listings), so a few thousand tokens of things
// nobody uses cost a few thousand tokens on every one of a session's hundreds of requests.
//
// Loaded by policy (managed prependPlugins, see templates/40-claude-lean-harness.json.j2): on a
// machine with managed settings the built-in guard sec-default keeps the prompt events away from
// any mod a user installs. The skill listing is trimmed by policy too, with skillOverrides in
// templates/10-claude-personal.json.j2: Claude Code does that natively, no mod needed.
//
// It only ever touches what ships with Claude Code: a tool from an MCP server or a plugin, an
// agent of yours and a plugin's prompt sections pass through untouched, even under a name it
// trims. Every rule names its target exactly; a target Claude Code renamed or reworded is left as
// shipped, and the tests in tests/ say which rule went dead. Every hook fails open: one that throws
// is skipped and Claude Code behaves as if the mod weren't there.

// ── tools ────────────────────────────────────────────────────────────────────────
// Each tool listed up front rides on every request. These serve features asked for by name
// (/loop, /code-review, a feedback report), so they wait behind ToolSearch and load when the
// model asks for one by name.
export const DEFER = ['ScheduleWakeup', 'SendFeedback', 'ReportFindings']

// Claude Code announces only the tools it defers itself; this line names the rest.
export const DEFERRED_ID = 'lean-harness:deferred'
export const deferredLine = (names) => `Also behind ToolSearch (load by name before use): ${names.join(', ')}.`

// ── agents ───────────────────────────────────────────────────────────────────────
// The status line is set by policy on these machines, so this agent can't change anything.
export const HIDDEN_AGENTS = ['statusline-setup']

// ── system prompt ────────────────────────────────────────────────────────────────
// Anthropic's server picks section variants per account and model and can switch them under the
// same version, so rules name a section by id and a line by its opening. Only the engine's own
// sections are touched: a plugin's carry a `plugin:` prefix.

// The model's marketing blurb (Fable's: the Mythos tier and a link); the model line in the first
// message already names the model.
export const DROP_SECTIONS = [{ why: 'model identity blurb', match: (id) => id.endsWith('_identity') }]

export const DROP_LINES = [
  { section: (id) => id === 'session_guidance', opening: ' - If the user asks about "ultrareview"' },
  { section: (id) => id.startsWith('env_info'), opening: ' - Claude Code is available as' },
  { section: (id) => id.startsWith('env_info'), opening: ' - Fast mode for Claude Code' },
]

// `<total_tokens>15000000 tokens left</total_tokens>` sits in the prompt and rides on every request
// after it. It tells the model something only when a real budget is set.
export const BUDGET_FLOOR = 1_000_000
export function isIdleBudget(text) {
  const m = /^<total_tokens>(\d+) tokens left<\/total_tokens>$/.exec((text ?? '').trim())
  return m !== null && Number(m[1]) >= BUDGET_FLOOR
}

const isEngineSection = (id) => typeof id === 'string' && !id.includes(':')

export function trimSections(sections, tools) {
  const out = []
  for (const sec of sections) {
    if (!isEngineSection(sec.id)) {
      out.push(sec)
      continue
    }
    if (DROP_SECTIONS.some((rule) => rule.match(sec.id))) continue
    if (sec.id === 'total_tokens' && isIdleBudget(sec.text)) continue
    const rules = DROP_LINES.filter((rule) => rule.section(sec.id))
    if (rules.length === 0) {
      out.push(sec)
      continue
    }
    const lines = sec.text.split('\n')
    const kept = lines.filter((line) => !rules.some((rule) => line.startsWith(rule.opening)))
    out.push(kept.length === lines.length ? sec : { ...sec, text: kept.join('\n') })
  }
  // Without ToolSearch (a gateway, some providers) every tool is sent in full and nothing waits.
  const deferred = tools.includes('ToolSearch') ? DEFER.filter((name) => tools.includes(name)) : []
  if (deferred.length > 0 && !out.some((sec) => sec.id === DEFERRED_ID)) out.push({ id: DEFERRED_ID, scope: 'session', text: deferredLine(deferred) })
  return out
}

export function register(on) {
  on('tool.describe', async ($, e, next) => {
    const r = await next(e)
    return e.provider?.plugin === 'engine' && DEFER.includes(e.tool) ? { ...r, isDeferred: true } : r
  })

  on('agent.offer', async ($, e, next) =>
    e.source === 'built-in' && e.provider?.plugin === 'engine' && HIDDEN_AGENTS.includes(e.agent) ? { isOffered: false } : next(e),
  )

  on('prompt.compose', async ($, e, next) => {
    const r = await next(e)
    return { ...r, sections: trimSections(r.sections, e.tools ?? []) }
  })

  on('prompt.attachment', { type: 'total_tokens_reminder' }, async ($, e, next) => (isIdleBudget(e.text) ? { text: null } : next(e)))
}
