import {defineCliConfig} from 'sanity/cli'
// separate studio host so v1 (hw-for-ai-lab.sanity.studio) stays untouched
export default defineCliConfig({
  api: {projectId: 'onwa0wvs', dataset: 'v2'},
  studioHost: 'hw-for-ai-lab-v2',
})
