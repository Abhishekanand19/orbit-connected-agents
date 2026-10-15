import os
import boto3
from botocore.exceptions import ClientError


def handler(event, context):
    if event.get('operation') == 'probe':
        try:
            credentials = boto3.client('sts').assume_role(
                RoleArn=os.environ['TARGET_ROLE'], RoleSessionName='pathlock-probe')['Credentials']
            client = boto3.client('secretsmanager',
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'])
            result = client.get_secret_value(SecretId=os.environ['SECRET_ARN'])
            return {'access': 'granted', 'demo_value_matches': result['SecretString'] == 'PATHLOCK_DEMO_SECRET_123'}
        except ClientError as error:
            code = error.response['Error']['Code']
            if code in ('AccessDenied', 'AccessDeniedException'):
                return {'access': 'denied', 'code': code}
            raise
    result = boto3.client('dynamodb').get_item(
        TableName=os.environ['ORDERS_TABLE'], Key={'order_id': {'S': '582'}})
    return {'order': '582', 'status': result['Item']['status']['S']}
