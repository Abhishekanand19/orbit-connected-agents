"""Provision a restricted runtime role using the operator profile once."""
import json
from backend.sandbox import SESSION, ROOT, TAGS

def provision():
    iam=SESSION.client('iam')
    identity=SESSION.client('sts').get_caller_identity()
    caller=identity['Arn']
    if ':assumed-role/' in caller:
        principal=iam.get_role(RoleName=caller.split(':assumed-role/')[1].split('/')[0])['Role']['Arn']
    else:principal=caller
    state=json.loads((ROOT/'.aws/sandbox.json').read_text())
    account=identity['Account']
    roles=[f'arn:aws:iam::{account}:role/pathlock-demo-{suffix}' for suffix in ('app','analytics','reporting')]
    trust={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'AWS':principal},'Action':'sts:AssumeRole'}]}
    role=iam.create_role(RoleName='pathlock-demo-controller',AssumeRolePolicyDocument=json.dumps(trust),Tags=TAGS)['Role']['Arn']
    document={'Version':'2012-10-17','Statement':[
        {'Effect':'Allow','Action':['iam:GetRole','iam:GetRolePolicy','iam:ListRolePolicies'],'Resource':roles},
        {'Effect':'Allow','Action':['iam:PutRolePolicy'],'Resource':roles[0]},
        {'Effect':'Allow','Action':['lambda:InvokeFunction','lambda:GetFunctionConfiguration','lambda:UpdateFunctionConfiguration'],'Resource':f'arn:aws:lambda:ap-southeast-2:{account}:function:pathlock-demo-order-support'},
        {'Effect':'Allow','Action':['iam:CreateRole','iam:TagRole','iam:PutRolePolicy'],'Resource':roles[2]},
        {'Effect':'Allow','Action':'bedrock:InvokeModel','Resource':'arn:aws:bedrock:ap-southeast-2::foundation-model/amazon.nova-micro-v1:0'}]}
    iam.put_role_policy(RoleName='pathlock-demo-controller',PolicyName='PathLockRuntime',PolicyDocument=json.dumps(document))
    (ROOT/'.aws/controller.json').write_text(json.dumps({'role':role}))
    print('Restricted runtime role created for existing demo resources.')

if __name__=='__main__':provision()
