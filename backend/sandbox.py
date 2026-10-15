"""Provision and test only the dedicated PathLock demo resources."""
import io
import json
import os
import time
import zipfile
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
os.environ['AWS_CONFIG_FILE'] = str(ROOT / '.aws/config')
os.environ['AWS_SHARED_CREDENTIALS_FILE'] = str(ROOT / '.aws/credentials')
os.environ['AWS_LOGIN_CACHE_DIRECTORY'] = str(ROOT / '.aws/login-cache')
SESSION = boto3.Session(profile_name='pathlock', region_name='ap-southeast-2')
if os.environ.get('PATHLOCK_RUNTIME') == '1':
    from botocore.credentials import RefreshableCredentials
    from botocore.session import get_session
    operator = SESSION
    runtime_role = json.loads((ROOT/'.aws/controller.json').read_text())['role']
    def refresh_runtime():
        value = operator.client('sts').assume_role(RoleArn=runtime_role,RoleSessionName='pathlock-runtime')['Credentials']
        return {'access_key':value['AccessKeyId'],'secret_key':value['SecretAccessKey'],'token':value['SessionToken'],'expiry_time':value['Expiration'].isoformat()}
    runtime = get_session()
    runtime._credentials = RefreshableCredentials.create_from_metadata(metadata=refresh_runtime(),refresh_using=refresh_runtime,method='sts-assume-role')
    runtime.set_config_variable('region','ap-southeast-2')
    SESSION = boto3.Session(botocore_session=runtime)
PREFIX = 'pathlock-demo'
TAGS = [{'Key': 'Project', 'Value': 'PathLock'}, {'Key': 'Purpose', 'Value': 'ControlledDemo'}]

def policy(action, resource):
    return json.dumps({'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Action': action, 'Resource': resource}]})

def provision():
    iam = SESSION.client('iam')
    db = SESSION.client('dynamodb')
    secrets = SESSION.client('secretsmanager')
    functions = SESSION.client('lambda')
    account = SESSION.client('sts').get_caller_identity()['Account']
    app_name = PREFIX + '-app'
    target_name = PREFIX + '-analytics'
    app_arn = f'arn:aws:iam::{account}:role/{app_name}'
    target_arn = f'arn:aws:iam::{account}:role/{target_name}'
    # Fail on name collisions rather than adopt unrelated existing resources.
    trust = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Service': 'lambda.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]}
    iam.create_role(RoleName=app_name, AssumeRolePolicyDocument=json.dumps(trust), Tags=TAGS)
    time.sleep(15)  # IAM principal propagation before referring to the new role.
    trust['Statement'][0]['Principal'] = {'AWS': app_arn}
    iam.create_role(RoleName=target_name, AssumeRolePolicyDocument=json.dumps(trust), Tags=TAGS)
    table = db.create_table(TableName=PREFIX+'-orders', KeySchema=[{'AttributeName': 'order_id', 'KeyType': 'HASH'}], AttributeDefinitions=[{'AttributeName': 'order_id', 'AttributeType': 'S'}], BillingMode='PAY_PER_REQUEST', Tags=TAGS)['TableDescription']['TableArn']
    db.get_waiter('table_exists').wait(TableName=PREFIX+'-orders')
    db.put_item(TableName=PREFIX+'-orders', Item={'order_id': {'S': '582'}, 'status': {'S': 'SHIPPED'}})
    secret = secrets.create_secret(Name=PREFIX+'-private-secret', SecretString='PATHLOCK_DEMO_SECRET_123', Tags=TAGS)['ARN']
    iam.put_role_policy(RoleName=app_name, PolicyName='OrderLookup', PolicyDocument=policy('dynamodb:GetItem', table))
    iam.put_role_policy(RoleName=app_name, PolicyName='DemoUnsafeRoute', PolicyDocument=policy('sts:AssumeRole', target_arn))
    iam.put_role_policy(RoleName=target_name, PolicyName='DemoSecretRead', PolicyDocument=policy('secretsmanager:GetSecretValue', secret))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.write(ROOT/'backend/order_handler.py', 'order_handler.py')
    state = {'app_role': app_name, 'target_role': target_name, 'app_arn': app_arn, 'target_arn': target_arn, 'table_arn': table, 'secret_arn': secret, 'function': PREFIX+'-order-support'}
    (ROOT/'.aws/sandbox.json').write_text(json.dumps(state, indent=2))
    for attempt in range(12):
        try:
            functions.create_function(FunctionName=state['function'], Runtime='python3.12', Role=app_arn, Handler='order_handler.handler', Code={'ZipFile': archive.getvalue()}, Timeout=20, MemorySize=128, Environment={'Variables': {'TARGET_ROLE': target_arn, 'SECRET_ARN': secret, 'ORDERS_TABLE': PREFIX+'-orders'}}, Tags={'Project': 'PathLock', 'Purpose': 'ControlledDemo'})
            break
        except ClientError as error:
            if error.response['Error']['Code'] != 'InvalidParameterValueException' or attempt == 11:
                raise
            time.sleep(5)
    functions.get_waiter('function_active_v2').wait(FunctionName=state['function'])
    print('Sandbox provisioned; no public probe endpoint.')

def probe(operation):
    state = json.loads((ROOT/'.aws/sandbox.json').read_text())
    result = SESSION.client('lambda').invoke(FunctionName=state['function'], Payload=json.dumps({'operation': operation}).encode())
    payload = json.loads(result['Payload'].read())
    if result.get('FunctionError'):
        raise RuntimeError('Lambda probe failed: '+str(payload.get('errorType')))
    return payload

if __name__ == '__main__':
    import sys
    if 'provision' in sys.argv:
        provision()
    order = probe('order')
    exposure = probe('probe')
    assert order == {'order': '582', 'status': 'SHIPPED'}, order
    assert exposure == {'access': 'granted', 'demo_value_matches': True}, exposure
    print('Phase 1: order SHIPPED; controlled secret access GRANTED.')
