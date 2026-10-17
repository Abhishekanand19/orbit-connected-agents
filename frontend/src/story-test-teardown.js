import {execFileSync} from 'node:child_process';
export default function teardown(config){const {python,graph,root}=config.metadata;execFileSync(python,['tests/orbit/story_fixture.py','--graph',graph,'--delete'],{cwd:root,stdio:'pipe'});}
