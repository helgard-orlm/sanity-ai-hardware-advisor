import {defineType, defineField, defineArrayMember} from 'sanity'

// v2 — "AI hardware advisor" knowledge base, built by an architect, FILLED BY A MODEL.
// Every field description below is written for the FILLER model: what the field means,
// where to get the value, and what to do when unsure.
//
// Three rules that hold for every document:
//  1. Empty field = UNKNOWN. Never write 0, "none" or a guess to fill a gap.
//  2. Every number must be traceable: document-level `sources` + `fieldSources` for fields
//     that come from a different source than the rest.
//  3. A URL is written ONLY if you actually opened that page in this session.
//     Otherwise leave url empty and set kind = "unverified".

// ---------- shared pieces ----------

const sources = defineField({
  name: 'sources', title: 'Sources', type: 'array',
  of: [defineArrayMember({type: 'reference', to: [{type: 'source'}]})],
  description: 'Where the values of this document come from. At least one. Strongest first.',
})

const fieldSources = defineField({
  name: 'fieldSources', title: 'Per-field sources', type: 'array',
  description: 'Use when some fields come from a different source than `sources`, or you are less sure about them.',
  of: [defineArrayMember({
    type: 'object', name: 'fieldSource',
    fields: [
      defineField({name: 'fields', type: 'array', of: [{type: 'string'}], description: 'Field names this applies to, e.g. ["memBandwidthGBs"].'}),
      defineField({name: 'source', type: 'reference', to: [{type: 'source'}]}),
      defineField({name: 'confidence', type: 'string', options: {list: ['high', 'medium', 'low']}}),
      defineField({name: 'note', type: 'string'}),
    ],
  })],
})

const status = defineField({
  name: 'status', type: 'string', initialValue: 'unverified',
  options: {list: ['unverified', 'checked', 'confirmed']},
  description: 'Filler always writes "unverified". "checked" = cross-checked against a second independent source. "confirmed" = set only by a human reviewer.',
})

// ---------- sources ----------

export const source = defineType({
  name: 'source', title: 'Source', type: 'document',
  fields: [
    defineField({name: 'title', type: 'string'}),
    defineField({name: 'kind', type: 'string',
      options: {list: ['measured', 'vendor', 'spec', 'benchmark', 'reported', 'derived', 'unverified']},
      description: 'measured = run on real hardware by the owner of this base; vendor = manufacturer page or official model card/repo; spec = reference spec database (TechPowerUp, Intel ARK...); AI-generated summaries (deepwiki etc.) are reported, never spec; benchmark = published benchmark with method; reported = forum/user report; derived = computed by a `law` from other values; unverified = not opened / not cross-checked.'}),
    defineField({name: 'url', type: 'url', description: 'Only a page you actually opened. Never a guessed or shortened link.'}),
    defineField({name: 'retrievedAt', type: 'date'}),
    defineField({name: 'note', type: 'text'}),
  ],
})

// ---------- workload side (what the person wants) ----------

export const aiModel = defineType({
  name: 'aiModel', title: 'AI model', type: 'document',
  description: 'A model a person may want to run. Fill from the model card (Hugging Face, vendor page).',
  fields: [
    defineField({name: 'name', type: 'string', description: 'Exact name as on the model card, with size, e.g. "Qwen3-8B".'}),
    defineField({name: 'family', type: 'string'}),
    defineField({name: 'modality', type: 'array', of: [{type: 'string'}],
      options: {list: ['chat', 'code', 'vision', 'image-gen', 'image-edit', 'music', 'tts', 'stt', 'video', 'embedding']}}),
    defineField({name: 'architecture', type: 'string', options: {list: ['dense', 'moe', 'diffusion', 'other']}}),
    defineField({name: 'paramsTotalB', type: 'number', description: 'Total parameters, billions.'}),
    defineField({name: 'paramsActiveB', type: 'number', description: 'MoE only: active parameters per token, billions. Dense: leave empty.'}),
    defineField({name: 'contextMax', type: 'number', description: 'Max context in tokens per model card.'}),
    defineField({name: 'numLayers', type: 'number', description: 'Transformer layers (config.json: num_hidden_layers). Needed for KV cache.'}),
    defineField({name: 'numKvHeads', type: 'number', description: 'KV heads (config.json: num_key_value_heads). Needed for KV cache.'}),
    defineField({name: 'headDim', type: 'number', description: 'Head dimension (config.json: head_dim, or hidden_size / num_attention_heads).'}),
    defineField({name: 'kvBytesPerToken', type: 'number', description: 'KV cache bytes per token at fp16 for this model = 2 * numLayers * numKvHeads * headDim * 2. For MLA/hybrid (Mamba) models write the value from the card/paper and explain in fieldSources.note.'}),
    defineField({name: 'toolCalling', type: 'string', options: {list: ['native', 'via-template', 'no']},
      description: 'Can it call tools/functions (needed for agents). Leave empty if the card does not say.'}),
    defineField({name: 'languages', type: 'array', of: [{type: 'string'}], description: 'ISO codes the card claims, e.g. en, ru, uk.'}),
    defineField({name: 'openWeights', type: 'boolean'}),
    defineField({name: 'license', type: 'string'}),
    defineField({name: 'releaseDate', type: 'date'}),
    defineField({name: 'variants', type: 'array', description: 'Downloadable files. One entry per format+bits.',
      of: [defineArrayMember({type: 'object', name: 'modelVariant', fields: [
        defineField({name: 'format', type: 'string', options: {list: ['gguf', 'safetensors', 'mlx', 'onnx', 'other']}}),
        defineField({name: 'bits', type: 'number', description: 'Effective bits per weight, e.g. 4.5 for Q4_K_M, 16 for bf16.'}),
        defineField({name: 'quantName', type: 'string', description: 'e.g. Q4_K_M, int8, NVFP4.'}),
        defineField({name: 'fileGb', type: 'number', description: 'Total download size in GB (sum of shards).'}),
        defineField({name: 'runtimes', type: 'array', of: [{type: 'reference', to: [{type: 'software'}]}]}),
      ]})]}),
    defineField({name: 'minRuntimeVersion', type: 'text', description: 'If the card says a runtime version is required (e.g. "llama.cpp >= b5000", "ComfyUI with support PR #16400"), write it here.'}),
    status, sources, fieldSources,
  ],
})

export const software = defineType({
  name: 'software', title: 'Software / runtime', type: 'document',
  fields: [
    defineField({name: 'name', type: 'string', description: 'e.g. Ollama, llama.cpp, ComfyUI, vLLM, LM Studio.'}),
    defineField({name: 'purpose', type: 'string'}),
    defineField({name: 'gpuBackends', type: 'array', of: [{type: 'string'}], options: {list: ['cuda', 'rocm', 'vulkan', 'metal', 'sycl', 'cpu']}}),
    defineField({name: 'os', type: 'array', of: [{type: 'string'}], options: {list: ['windows', 'linux', 'macos']}}),
    defineField({name: 'cpuRequires', type: 'array', of: [{type: 'string'}], description: 'CPU instruction sets the official builds require, e.g. ["AVX2"]. Empty = unknown.'}),
    defineField({name: 'minCudaComputeCapability', type: 'number', description: 'e.g. 5.0. And the newest arch it supports goes to notes.'}),
    defineField({name: 'installEffort', type: 'string', options: {list: ['one-click', 'some-setup', 'expert']}}),
    defineField({name: 'notes', type: 'text'}),
    status, sources, fieldSources,
  ],
})

export const useCase = defineType({
  name: 'useCase', title: 'Use case', type: 'document',
  description: 'A kind of job people ask for ("chat with an 8B model", "home + office agent", "image generation"). Describes NEEDS, never hardware.',
  fields: [
    defineField({name: 'name', type: 'string'}),
    defineField({name: 'description', type: 'text'}),
    defineField({name: 'modalities', type: 'array', of: [{type: 'string'}]}),
    defineField({name: 'needsToolCalling', type: 'boolean'}),
    defineField({name: 'loadProfile', type: 'string', options: {list: ['on-demand-single-user', 'always-on-single-user', 'multi-user']}}),
    defineField({name: 'typicalContextTokens', type: 'number'}),
    defineField({name: 'acceptableSpeed', type: 'string', description: 'In the unit of the modality, e.g. ">= 10 tok/s", "<= 60 s per image".'}),
    defineField({name: 'candidateModels', type: 'array', of: [{type: 'reference', to: [{type: 'aiModel'}]}]}),
    defineField({name: 'situationKeys', type: 'array', of: [{type: 'string'}],
      description: 'Keys from situationTemplate that change the answer for this use case, most important first.'}),
    defineField({name: 'integrations', type: 'array', of: [{type: 'string'}], description: 'e.g. Home Assistant, Microsoft Office, LibreOffice.'}),
    defineField({name: 'risks', type: 'array', of: [{type: 'string'}], description: 'Non-hardware risks, e.g. "agent gets control over the house".'}),
    status, sources,
  ],
})

// ---------- hardware side (what things can do) ----------

export const gpu = defineType({
  name: 'gpu', title: 'Graphics card', type: 'document',
  fields: [
    defineField({name: 'name', type: 'string', description: 'Chip-level name, e.g. "GeForce RTX 5060 8 GB". Vendor board variants are not separate entries unless memory differs.'}),
    defineField({name: 'vendor', type: 'string', options: {list: ['nvidia', 'amd', 'intel']}}),
    defineField({name: 'architecture', type: 'string', description: 'e.g. Blackwell, Ada, RDNA4.'}),
    defineField({name: 'cudaComputeCapability', type: 'number', description: 'NVIDIA only, e.g. 12.0 for RTX 50.'}),
    defineField({name: 'releaseYear', type: 'number'}),
    defineField({name: 'vramGb', type: 'number'}),
    defineField({name: 'memBandwidthGBs', type: 'number', description: 'Memory bandwidth GB/s. Sets the ceiling on LLM tokens/s.'}),
    defineField({name: 'pcieGen', type: 'number'}),
    defineField({name: 'pcieLanes', type: 'number', description: 'Electrical lanes of the card (x8 / x16). Matters on old boards.'}),
    defineField({name: 'boardPowerW', type: 'number'}),
    defineField({name: 'recommendedPsuW', type: 'number', description: 'From the vendor page. If you only have a derived number, put it in notes, not here.'}),
    defineField({name: 'powerConnector', type: 'string', description: 'e.g. "1x 8-pin", "16-pin 12V-2x6", "none (slot only)".'}),
    defineField({name: 'lengthMm', type: 'number'}),
    defineField({name: 'slots', type: 'number'}),
    defineField({name: 'idleW', type: 'number'}),
    defineField({name: 'notes', type: 'text'}),
    status, sources, fieldSources,
  ],
})

export const cpu = defineType({
  name: 'cpu', title: 'CPU', type: 'document',
  fields: [
    defineField({name: 'name', type: 'string'}),
    defineField({name: 'releaseYear', type: 'number'}),
    defineField({name: 'socket', type: 'string'}),
    defineField({name: 'cores', type: 'number'}),
    defineField({name: 'instructionSets', type: 'array', of: [{type: 'string'}],
      description: 'COMPLETE list from the vendor page (SSE4.2, AVX, AVX2, AVX-512, FMA...). A set not listed = NOT supported, so never write a partial list.'}),
    defineField({name: 'memoryTypes', type: 'array', of: [{type: 'string'}]}),
    defineField({name: 'memChannels', type: 'number'}),
    defineField({name: 'maxRamGb', type: 'number'}),
    defineField({name: 'hasIntegratedGpu', type: 'boolean'}),
    defineField({name: 'npuTops', type: 'number'}),
    defineField({name: 'pcieGen', type: 'number'}),
    defineField({name: 'notes', type: 'text'}),
    status, sources, fieldSources,
  ],
})

export const system = defineType({
  name: 'system', title: 'Whole system', type: 'document',
  description: 'Anything bought as one box: Mac, mini-PC, office PC (Dell SFF...), laptop, AI workstation. Also the base owner\'s own test machine.',
  fields: [
    defineField({name: 'name', type: 'string'}),
    defineField({name: 'kind', type: 'string', options: {list: ['desktop', 'sff-office', 'mini-pc', 'laptop', 'mac', 'workstation', 'server']}}),
    defineField({name: 'cpu', type: 'reference', to: [{type: 'cpu'}]}),
    defineField({name: 'gpu', type: 'reference', to: [{type: 'gpu'}]}),
    defineField({name: 'unifiedMemoryGb', type: 'number', description: 'Memory shared by CPU and GPU (Apple Silicon, AMD Strix Halo). Empty for normal PCs.'}),
    defineField({name: 'memBandwidthGBs', type: 'number'}),
    defineField({name: 'ramGb', type: 'number'}),
    defineField({name: 'ramUpgradeable', type: 'boolean'}),
    defineField({name: 'gpuSlot', type: 'string', options: {list: ['full-height', 'low-profile-only', 'none']}}),
    defineField({name: 'psuW', type: 'number'}),
    defineField({name: 'psuHasGpuConnector', type: 'boolean'}),
    defineField({name: 'os', type: 'string'}),
    defineField({name: 'notes', type: 'text'}),
    status, sources, fieldSources,
  ],
})

// ---------- money side ----------

export const offer = defineType({
  name: 'offer', title: 'Price offer', type: 'document',
  description: 'One price, in one shop, on one date. Prices are never stored on the product itself.',
  fields: [
    defineField({name: 'product', type: 'reference', to: [{type: 'gpu'}, {type: 'cpu'}, {type: 'system'}]}),
    defineField({name: 'price', type: 'number'}),
    defineField({name: 'currency', type: 'string', description: 'ISO code: USD, EUR, UAH...'}),
    defineField({name: 'region', type: 'string', description: 'Country code, e.g. UA, US, DE.'}),
    defineField({name: 'condition', type: 'string', options: {list: ['new', 'used', 'refurbished']}}),
    defineField({name: 'shop', type: 'string'}),
    defineField({name: 'date', type: 'date'}),
    sources,
  ],
})

export const cloudOffer = defineType({
  name: 'cloudOffer', title: 'Cloud / API option', type: 'document',
  description: 'The "do not buy" branch: pay-per-token API or rented GPU.',
  fields: [
    defineField({name: 'name', type: 'string'}),
    defineField({name: 'kind', type: 'string', options: {list: ['api', 'gpu-rent']}}),
    defineField({name: 'model', type: 'reference', to: [{type: 'aiModel'}], description: 'For api.'}),
    defineField({name: 'gpu', type: 'reference', to: [{type: 'gpu'}], description: 'For gpu-rent.'}),
    defineField({name: 'priceInputPerMTok', type: 'number'}),
    defineField({name: 'priceOutputPerMTok', type: 'number'}),
    defineField({name: 'pricePerHour', type: 'number'}),
    defineField({name: 'currency', type: 'string'}),
    defineField({name: 'dataPolicy', type: 'text', description: 'Does the provider keep or train on data. Quote the page.'}),
    defineField({name: 'date', type: 'date'}),
    sources,
  ],
})

// ---------- evidence ----------

export const runReport = defineType({
  name: 'runReport', title: 'Run report', type: 'document',
  description: 'One real run: this model variant, on this hardware, with this software and settings → what happened. Measured by the owner = strongest evidence; published benchmarks = kind "benchmark".',
  fields: [
    defineField({name: 'model', type: 'reference', to: [{type: 'aiModel'}]}),
    defineField({name: 'quantName', type: 'string'}),
    defineField({name: 'system', type: 'reference', to: [{type: 'system'}]}),
    defineField({name: 'gpu', type: 'reference', to: [{type: 'gpu'}]}),
    defineField({name: 'software', type: 'reference', to: [{type: 'software'}]}),
    defineField({name: 'softwareVersion', type: 'string'}),
    defineField({name: 'contextTokens', type: 'number'}),
    defineField({name: 'placement', type: 'string', description: 'e.g. "100% GPU", "hybrid 80% CPU / 20% GPU", "CPU only".'}),
    defineField({name: 'works', type: 'string', options: {list: ['yes', 'degraded', 'no']}}),
    defineField({name: 'failure', type: 'string', description: 'If works != yes: OOM, crash, garbage output, too slow...'}),
    defineField({name: 'peakVramGb', type: 'number'}),
    defineField({name: 'peakRamGb', type: 'number'}),
    defineField({name: 'tokensPerSec', type: 'number'}),
    defineField({name: 'secondsPerItem', type: 'number', description: 'Image/clip/song: seconds per one item.'}),
    defineField({name: 'itemDescription', type: 'string', description: 'e.g. "1024x1024 image, 20 steps", "5 s video 832x480".'}),
    defineField({name: 'notes', type: 'text'}),
    sources,
  ],
})

export const law = defineType({
  name: 'law', title: 'Law / formula', type: 'document',
  description: 'A calculation the answering model must show, e.g. weights size, KV cache, speed ceiling, electricity cost.',
  fields: [
    defineField({name: 'name', type: 'string'}),
    defineField({name: 'formula', type: 'string', description: 'ONE Python expression (no "=" and no ";") using only the variable names below, e.g. "paramsB * bits / 8". Two results = two laws.'}),
    defineField({name: 'resultUnit', type: 'string'}),
    defineField({name: 'variables', type: 'array', of: [defineArrayMember({type: 'object', name: 'lawVariable', fields: [
      defineField({name: 'name', type: 'string'}),
      defineField({name: 'meaning', type: 'string'}),
      defineField({name: 'unit', type: 'string'}),
      defineField({name: 'takeFrom', type: 'string', description: 'Where the value comes from: a path "aiModel.paramsTotalB", "aiModel.variants.bits" (field inside a list), "situation.electricityPrice", or "constant 1.2" (a number only). The variable `name` must be exactly the name used in `formula`.'}),
    ]})]}),
    defineField({name: 'validity', type: 'text', description: 'When the formula is wrong or rough (e.g. "MoE: use active params for speed, total for memory").'}),
    defineField({name: 'workedExample', type: 'text', description: 'One example with real numbers, preferably checked against a runReport.'}),
    status, sources,
  ],
})

export const rule = defineType({
  name: 'rule', title: 'Rule', type: 'document',
  description: 'A machine-checkable condition. Left and right side may only name fields that EXIST in this schema or keys of situationTemplate. No prose in `check`.',
  fields: [
    defineField({name: 'title', type: 'string'}),
    defineField({name: 'check', type: 'object', fields: [
      defineField({name: 'left', type: 'string', description: 'Path like "gpu.vramGb", "cpu.instructionSets", "situation.cloudAllowed".'}),
      defineField({name: 'op', type: 'string', options: {list: ['>=', '<=', '==', '!=', 'contains', 'notContains', 'in', 'isEmpty']}}),
      defineField({name: 'right', type: 'string', description: 'A literal ("AVX2", "8") or another path ("software.minCudaComputeCapability").'}),
    ]}),
    defineField({name: 'appliesWhen', type: 'string', description: 'Optional second check in the same syntax, e.g. "software.gpuBackends contains cuda".'}),
    defineField({name: 'severity', type: 'string', options: {list: ['blocks', 'unreliable', 'degrades', 'risk']}}),
    defineField({name: 'consequence', type: 'text', description: 'Plain words for the person. Phrase as "risk, check before buying", not "useless".'}),
    defineField({name: 'askIfUnknown', type: 'string', description: 'The question in plain words if the left value is unknown.'}),
    defineField({name: 'howToCheck', type: 'text', description: 'How the person can check it themselves (a command, a sticker, a menu).'}),
    defineField({name: 'workaround', type: 'text'}),
    status, sources,
  ],
})

export const failureCase = defineType({
  name: 'failureCase', title: 'Failure case', type: 'document',
  description: 'A real story where a setup looked fine on paper and failed. Used to warn before buying.',
  fields: [
    defineField({name: 'title', type: 'string'}),
    defineField({name: 'setup', type: 'text'}),
    defineField({name: 'whatHappened', type: 'text'}),
    defineField({name: 'rootCause', type: 'text'}),
    defineField({name: 'relatedRules', type: 'array', of: [{type: 'reference', to: [{type: 'rule'}]}]}),
    sources,
  ],
})

// ---------- the person ----------

export const situationTemplate = defineType({
  name: 'situationTemplate', title: 'Situation template', type: 'document',
  description: 'What the advisor must know about the PERSON. One document. Keys are referenced by rules, laws and use cases as "situation.<key>".',
  fields: [
    defineField({name: 'title', type: 'string'}),
    defineField({name: 'items', type: 'array', of: [defineArrayMember({type: 'object', name: 'situationItem', fields: [
      defineField({name: 'key', type: 'string', description: 'camelCase, e.g. budgetAmount.'}),
      defineField({name: 'valueType', type: 'string', options: {list: ['number', 'string', 'boolean', 'list', 'hardware-description']}}),
      defineField({name: 'question', type: 'string', description: 'How to ask it in plain words.'}),
      defineField({name: 'why', type: 'string', description: 'Which rules/laws/decisions depend on it.'}),
      defineField({name: 'priority', type: 'number', description: '1 = always needed, 2 = often, 3 = only for some use cases.'}),
      defineField({name: 'defaultIfUnknown', type: 'string', description: 'What the direct-answer mode assumes, stated as a condition in the answer.'}),
    ]})]}),
  ],
})

// ---------- new knowledge produced while answering ----------

export const derivedConcept = defineType({
  name: 'derivedConcept', title: 'Derived concept', type: 'document',
  description: 'A conclusion the model built from other documents that the base did not state directly. Always starts unverified; a human confirms.',
  fields: [
    defineField({name: 'claim', type: 'text'}),
    defineField({name: 'conditions', type: 'text', description: 'When it holds.'}),
    defineField({name: 'dependsOn', type: 'array', of: [{type: 'reference', to: [
      {type: 'aiModel'}, {type: 'gpu'}, {type: 'cpu'}, {type: 'system'}, {type: 'software'}, {type: 'runReport'}, {type: 'law'}, {type: 'rule'},
    ]}]}),
    defineField({name: 'howToVerify', type: 'text'}),
    defineField({name: 'impact', type: 'string', options: {list: ['changes-purchase', 'changes-setup', 'informational']}}),
    defineField({name: 'createdBy', type: 'string'}),
    status,
  ],
})

// ---------- the space of answers (v3, risk R2 "narrow frame") ----------

export const solutionPath = defineType({
  name: 'solutionPath', title: 'Solution path', type: 'document',
  description: 'One CLASS of answer to "what should I run this on". The advisor must walk through EVERY solutionPath for every request and say yes/no/maybe with numbers, so the width of the answer does not depend on how curious the model is. One document per class; the list of classes is given by the architect.',
  fields: [
    defineField({name: 'name', type: 'string'}),
    defineField({name: 'pathClass', type: 'string', options: {list: [
      'keep-existing', 'upgrade-existing', 'used-hardware', 'new-single-gpu', 'multi-gpu',
      'unified-memory', 'cpu-ram-offload-moe', 'cpu-only-small', 'smaller-model',
      'cloud-api', 'cloud-gpu-rent',
    ]}, description: 'Exactly one class per document.'}),
    defineField({name: 'idea', type: 'text', description: 'The path in 1-3 plain sentences, e.g. "keep the MoE experts in system RAM and the attention layers on one GPU".'}),
    defineField({name: 'fitsWhen', type: 'text', description: 'Conditions under which this path is a real option, in terms of fields and situation keys (model size, active params, budget, usage frequency, privacy, existing hardware).'}),
    defineField({name: 'failsWhen', type: 'text', description: 'Conditions that rule it out or make it a bad deal. Include the numbers.'}),
    defineField({name: 'decidingLaws', type: 'array', of: [{type: 'reference', to: [{type: 'law'}]}], description: 'Laws that decide yes/no for this path (memory, speed ceiling, cost over time).'}),
    defineField({name: 'decidingRules', type: 'array', of: [{type: 'reference', to: [{type: 'rule'}]}]}),
    defineField({name: 'software', type: 'array', of: [{type: 'reference', to: [{type: 'software'}]}], description: 'Runtimes that make this path possible (e.g. llama.cpp tensor override, KTransformers, MLX).'}),
    defineField({name: 'examples', type: 'array', of: [{type: 'reference', to: [{type: 'system'}, {type: 'gpu'}, {type: 'cloudOffer'}, {type: 'runReport'}]}], description: 'Reference examples already in the base. Do not create new catalog items only to fill this.'}),
    defineField({name: 'costShape', type: 'string', options: {list: ['none', 'one-time', 'monthly', 'per-use']}}),
    defineField({name: 'typicalTradeoff', type: 'text', description: 'What the person gives up (speed, noise, privacy, effort), with numbers when known.'}),
    status, sources,
  ],
})

export const schemaTypes = [
  source, aiModel, software, useCase,
  gpu, cpu, system,
  offer, cloudOffer,
  runReport, law, rule, failureCase,
  situationTemplate, derivedConcept,
  solutionPath,
]
