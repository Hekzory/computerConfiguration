// probe: writes what Claude Code composes, offers and lists, for lean-harness's checks.
// Loaded as a --plugin-dir mod by check.mjs (offline, user tier: its own calls only) and seated by
// policy by capture.py (logged in, outermost: it also sees every attachment as the engine made it).
// Files go to the folder in $PROBE_OUT: session.json at start, late.json a few seconds later,
// events.json after each event, done when the first turn completes.

const MODELS = ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-fable-5-1', 'claude-haiku-5-5']
const ATTACHMENTS = ['skill_listing', 'agent_listing_delta', 'deferred_tools_delta', 'total_tokens_reminder', 'mcp_instructions_delta']

const events = { attachments: {}, tools: {}, agents: {}, compose: [] }

async function outDir($) {
  return (await $.env.get('PROBE_OUT')) ?? null
}

async function write($, name, data) {
  const dir = await outDir($)
  if (dir !== null) await $.fs.write(`${dir}/${name}`, JSON.stringify(data, null, 1))
}

async function snapshot($) {
  const data = { compose: {}, errors: [] }
  for (const model of MODELS) {
    try {
      data.compose[model] = (await $.prompt.compose({ model, promptModel: model })).sections
    } catch (err) {
      data.errors.push(`compose ${model}: ${err}`)
    }
  }
  try {
    data.tools = (await $.tool.list()).map((t) => t.name)
  } catch (err) {
    data.errors.push(`tools: ${err}`)
  }
  try {
    data.commands = (await $.command.list()).map((c) => ({ name: c.name, source: c.source, plugin: c.plugin ?? null }))
  } catch (err) {
    data.errors.push(`commands: ${err}`)
  }
  return data
}

export function register(on) {
  on('session.start', async ($, e, next) => {
    const r = await next(e)
    await write($, 'session.json', { session: e, ...(await snapshot($)) })
    $.clock.after(8000, async () => write($, 'late.json', await snapshot($)))
    return r
  })

  on('prompt.attachment', async ($, e, next) => {
    const r = await next(e)
    if (ATTACHMENTS.includes(e.type) && !(e.type in events.attachments)) {
      events.attachments[e.type] = { raw: e.text, out: r.text }
      await write($, 'events.json', events)
    }
    return r
  })

  on('prompt.compose', async ($, e, next) => {
    const r = await next(e)
    events.compose.push({ model: e.model, tools: e.tools, traits: e.traits, sections: r.sections })
    await write($, 'events.json', events)
    return r
  })

  on('tool.describe', async ($, e, next) => {
    const r = await next(e)
    events.tools[e.tool] = { provider: e.provider, isDeferred: e.isDeferred ?? false, outDeferred: r.isDeferred ?? null }
    await write($, 'events.json', events)
    return r
  })

  on('agent.offer', async ($, e, next) => {
    const r = await next(e)
    events.agents[e.agent] = { description: e.description, source: e.source, provider: e.provider, offered: r.isOffered }
    await write($, 'events.json', events)
    return r
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    await write($, 'done', { at: await $.clock.now() })
    return r
  })
}
