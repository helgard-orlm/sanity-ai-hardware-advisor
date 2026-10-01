import {defineConfig} from 'sanity'
import {structureTool} from 'sanity/structure'
import {schemaTypes} from './schemaTypes'

export default defineConfig({
  name: 'v2',
  title: 'hw-for-ai-lab v2',
  projectId: 'onwa0wvs',
  dataset: 'v2',
  plugins: [structureTool()],
  schema: {types: schemaTypes},
})
