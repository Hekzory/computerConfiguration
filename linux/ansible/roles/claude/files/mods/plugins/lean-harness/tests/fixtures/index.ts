// Every captured fixture, oldest first. Written by tests/live/capture.py.
import { FIXTURE as v2_1_300 } from './v2.1.300.ts'
import { FIXTURE as v2_1_304 } from './v2.1.304.ts'

export const FIXTURES = [v2_1_300, v2_1_304]
export const LATEST = FIXTURES[FIXTURES.length - 1]
