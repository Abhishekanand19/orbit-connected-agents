import base from './playwright.graph.config.js';
const graph=base.metadata.graph.replace('orbit_test_visuals_','orbit_test_story_');
export default {...base,testMatch:['story.spec.js','workspace.spec.js','onboarding.spec.js'],timeout:90000,globalTeardown:'./src/story-test-teardown.js',metadata:{...base.metadata,graph},webServer:[
 {...base.webServer[0],command:`"${base.metadata.python}" tests/orbit/story_fixture.py --graph ${graph}`},base.webServer[1]
]};
