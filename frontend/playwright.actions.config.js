import base from './playwright.graph.config.js';
export default {...base,testMatch:'approval.spec.js',webServer:[
 {...base.webServer[0],command:`"${base.metadata.python}" tests/orbit/action_fixture.py --graph ${base.metadata.graph}`},
 base.webServer[1]
]};
