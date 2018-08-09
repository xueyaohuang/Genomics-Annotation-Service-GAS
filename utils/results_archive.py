import os
import json
import boto3
import time
from datetime import datetime
from botocore.client import Config
from flask import Flask
from boto3.dynamodb.conditions import Key
import configparser


# app = Flask(__name__)
# app.config.from_object(os.environ['GAS_SETTINGS'])

def archive_to_glacier():
    config = configparser.ConfigParser()
    config.read('configini.ini')
    aws_config = config['AWS']
    canceled_archive = []
    # Connect to SQS and get the message queue
    try:
        sqs = boto3.resource('sqs', region_name=aws_config['AWS_REGION_NAME'])
        huangxy_queue = sqs.get_queue_by_name(QueueName=aws_config['AWS_SQS_GLACIER'])
    except Exception as e:
        print(e)
        return
    # Poll the message queue in a loop
    while True:
        # Attempt to read a message from the queue
        response = huangxy_queue.receive_messages(WaitTimeSeconds=20)
        # If message read, extract job parameters from the message body as before
        if response:
            print('Get response successfully.')
            try:
                msg = json.loads(json.loads(response[0].body)['Message'])
                job_id = msg['job_id']                
            except Exception as e:
                raise e
                return
            # if the job should be canceled to put into archive, continue to the next while loop.
            if 'canceled_archive' in msg:
                canceled_archive.append(msg['canceled_archive'])
                response[0].delete()
                print('This job should not be moved to glacier.')
                continue
            # intercept the canceled archive job
            if job_id in canceled_archive:
                canceled_archive.remove(job_id)
                response[0].delete()
                print('Avoid moving to glacier.')
                continue
            try:
                dynamodb = boto3.resource('dynamodb', region_name=aws_config['AWS_REGION_NAME'])
                annotation_table = dynamodb.Table(aws_config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
                job = annotation_table.query(Select='ALL_ATTRIBUTES', KeyConditionExpression=Key('job_id').eq(job_id))['Items'][0]
                print('Get job successfully.')
            except Exception as e:
                raise e
                return
            if 'complete_time' in job and (time.time() - float(job['complete_time'])) > float(aws_config['FREE_USER_DATA_RETENTION']):
                try:
                    key = msg['s3_key_input_file'].replace('.vcf', '.annot.vcf')
                    s3 = boto3.resource('s3')
                    bucket = s3.Bucket(aws_config['AWS_S3_RESULTS_BUCKET'])
                    body = bucket.Object(key).get()['Body'].read()
                    # print(body)
                    client_glacier = boto3.client('glacier', aws_config['AWS_REGION_NAME'])
                    # Response Syntax
                    # {
                    #     'location': 'string',
                    #     'checksum': 'string',
                    #     'archiveId': 'string'
                    # }
                    glacier_upload_response = client_glacier.upload_archive(vaultName=aws_config['AWS_GLACIER_VAULT'], body=body)
                    print('Upload glacier successfully.')
                except Exception as e:
                    raise e
                    return
                try:
                    client_s3 = boto3.client('s3', region_name=aws_config['AWS_REGION_NAME'], config=Config(signature_version='s3v4'))
                    # Response Syntax
                    # {
                    #     'DeleteMarker': True|False,
                    #     'VersionId': 'string',
                    #     'RequestCharged': 'requester'
                    # }
                    s3_delete_response = client_s3.delete_object(Bucket=aws_config['AWS_S3_RESULTS_BUCKET'], Key=key)
                    print('Delete from s3 successfully.')
                except Exception as e:
                    raise e
                    return
                annotation_table.update_item(Key={'job_id':job_id}, AttributeUpdates={'archive_id': {'Value':glacier_upload_response['archiveId'], 'Action': 'PUT'}})
                print('Update database successfully.')
                # After all done, delete SQS
                response[0].delete()
                print('Delete SQS successfully.')
        else:
            print('There is no response.')
if __name__ == '__main__':
    archive_to_glacier()   






