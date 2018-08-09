import simplejson as json
import os
import boto3
import subprocess
import configparser

def send_email_ses(recipients=None, sender=None, subject=None, body=None):

  config = configparser.ConfigParser()
  config.read('configini.ini')
  aws_config = config['AWS']

  ses = boto3.client('ses', region_name=aws_config['AWS_REGION_NAME'])

  response = ses.send_email(
    Destination = {'ToAddresses': recipients},
    Message={
      'Body': {'Text': {'Charset': "UTF-8", 'Data': body}},
      'Subject': {'Charset': "UTF-8", 'Data': subject},
    },
    Source=sender)
  return response['ResponseMetadata']['HTTPStatusCode']

def email_notify():

    config = configparser.ConfigParser()
    config.read('configini.ini')
    aws_config = config['AWS']
    # Connect to SQS and get the message queue
    try:
        sqs = boto3.resource('sqs', region_name=aws_config['AWS_REGION_NAME'])
        huangxy_queue = sqs.get_queue_by_name(QueueName=aws_config['AWS_SQS_JOB_COMPLETE'])
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
            # get job information
            try:
                # msg = json.loads(response[0].body)
                message = json.loads(json.loads(response[0].body)['Message'])
                if not message:
                    print('No message.')
                print('Extract message successfully.')
            except Exception as e:
                print(e)
                return
            # send email notification
            try:
                job_id = message['job_id']
                url = 'https://huangxy.ucmpcs.org/annotations/' + job_id
                send_email_ses(recipients=['hxyqbsmile@gmail.com'], sender=aws_config['MAIL_DEFAULT_SENDER'], subject='Finish annotation successfully.', 
                               body='Dear user:\n Your job: %s, has been completed!\n You can see the details at %s' % (job_id, url))
                print('Send email successfully.')
            except Exception as e:
                print(e)
                return
            # delete the message after it is sent.
            try:
                response[0].delete()
                print('Delete message successfully.')
            except Exception as e:
                print(e)
                return
        else:
            print('There is no response.')
if __name__ == '__main__':
    email_notify()