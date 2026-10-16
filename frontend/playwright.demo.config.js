import base from './playwright.graph.config.js';
const graph=base.metadata.graph.replace('orbit_test_visuals_','orbit_test_demo_');
export default {...base,testMatch:'demo.spec.js',globalTeardown:'./src/demo-test-teardown.js',metadata:{...base.metadata,graph},webServer:[
 {...base.webServer[0],command:`"${base.metadata.python}" tests/orbit/demo_fixture.py --graph ${graph}`},base.webServer[1]
]};
