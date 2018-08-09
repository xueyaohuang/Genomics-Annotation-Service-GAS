import os
import json
import boto3
import time
from datetime import datetime
from botocore.client import Config
from boto3.dynamodb.conditions import Key, Attr
import configparser

def archive_restore():
    config = configparser.ConfigParser()
    config.read('configini.ini')
    aws_config = config['AWS']
    ## Connect to SQS and get the message queue
    try:
        sqs = boto3.resource('sqs', region_name=aws_config['AWS_REGION_NAME'])
        huangxy_queue = sqs.get_queue_by_name(QueueName=aws_config['AWS_SQS_ARCHIVE_RETRIEVE'])
    except Exception as e:
        raise e
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
                retrieve_id = msg['JobId']
                archive_id = msg['ArchiveId']
            except Exception as e:
                raise e
                return
            try:
                client_glacier = boto3.client('glacier', region_name=aws_config['AWS_REGION_NAME'])
                glacier_job_output = client_glacier.get_job_output(vaultName=aws_config['AWS_GLACIER_VAULT'], jobId=retrieve_id)
                print('Get job out of glacier successfully.')
            except Exception as e:
                raise e
                return
            # archive_id is not a key, so I can only use table scan to get the s3_result_key and job_id.
            try:
                dynamodb = boto3.resource('dynamodb', region_name=aws_config['AWS_REGION_NAME'])
                annotation_table = dynamodb.Table(aws_config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
                res =  annotation_table.scan(FilterExpression=Attr('archive_id').eq(archive_id))
                if not res['Items']:
                    response[0].delete()
                    print('No annotation.')
                else:
                    s3_result_key = str(res['Items'][0]['s3_key_result_file'])
                    job_id = res['Items'][0]['job_id']
            except Exception as e:
                raise e
                return 
            # put job to s3 again
            try:
                client_s3 = boto3.client('s3', region_name=aws_config['AWS_REGION_NAME'], config=Config(signature_version='s3v4'))
                # Response Syntax
                # {
                #     'DeleteMarker': True|False,
                #     'VersionId': 'string',
                #     'RequestCharged': 'requester'
                # }
                s3_upload_response = client_s3.put_object(Body=glacier_job_output['body'].read(), Bucket=aws_config['AWS_S3_RESULTS_BUCKET'],
                                                          Key=s3_result_key)
                print('Upload to S3 successfully.')
            except Exception as e:
                raise e
                return
            # update database.
            try:
                annotation_table.update_item(Key={'job_id': job_id}, AttributeUpdates={'archive_id': {'Action': 'DELETE'}})
                print('Update database successfully.')
            except Exception as e:
                raise e
                return     
            # After all done, delete SQS
            response[0].delete()
            print('Delete SQS successfully.')
        else:
            print('There is no response.')
if __name__ == '__main__':
    archive_restore()   






