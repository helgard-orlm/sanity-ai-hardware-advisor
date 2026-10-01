// Local GROQ over a dataset snapshot (NDJSON export). Query on stdin, JSON result on stdout.
// Used to replay the "before" state of the base (the Free plan has only two datasets).
import {parse, evaluate} from 'groq-js'
import fs from 'fs'
const docs = fs.readFileSync(process.argv[2], 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l))
const q = fs.readFileSync(0, 'utf8')
try {
  const r = await (await evaluate(parse(q), {dataset: docs})).get()
  process.stdout.write(JSON.stringify({result: r}))
} catch (e) { process.stdout.write(JSON.stringify({error: String(e).slice(0, 1500)})) }
