# views.py
#
# Copyright (C) 2011-2018 Vas Vasiliadis
# University of Chicago
#
# Application logic for the GAS
#
###
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import uuid
import time
import json
from datetime import datetime

import boto3
from botocore.client import Config
from boto3.dynamodb.conditions import Key

from flask import (abort, flash, redirect, render_template, 
  request, session, url_for)

from gas import app, db
from decorators import authenticated, is_premium
from auth import get_profile, update_profile


"""Start annotation request
Create the required AWS S3 policy document and render a form for
uploading an annotation input file using the policy document
"""
@app.route('/annotate', methods=['GET'])
@authenticated
def annotate():
  # Open a connection to the S3 service
  s3 = boto3.client('s3', 
    region_name=app.config['AWS_REGION_NAME'], 
    config=Config(signature_version='s3v4'))

  bucket_name = app.config['AWS_S3_INPUTS_BUCKET']
  user_id = session['primary_identity']

  # Generate unique ID to be used as S3 key (name)
  key_name = app.config['AWS_S3_KEY_PREFIX'] + user_id + '/' + str(uuid.uuid4()) + '~${filename}'

  # Redirect to a route that will call the annotator
  redirect_url = str(request.url) + "/job"

  # Define policy conditions
  # NOTE: We also must inlcude "x-amz-security-token" since we're
  # using temporary credentials via instance roles
  encryption = app.config['AWS_S3_ENCRYPTION']
  acl = app.config['AWS_S3_ACL']
  expires_in = app.config['AWS_SIGNED_REQUEST_EXPIRATION']
  fields = {
    "success_action_redirect": redirect_url,
    "x-amz-server-side-encryption": encryption,
    "acl": acl
  }
  conditions = [
    ["starts-with", "$success_action_redirect", redirect_url],
    {"x-amz-server-side-encryption": encryption},
    {"acl": acl}
  ]

  # Generate the presigned POST call
  presigned_post = s3.generate_presigned_post(Bucket=bucket_name, 
    Key=key_name, Fields=fields, Conditions=conditions, ExpiresIn=expires_in)

  # Set upload file size for free user and premium user 
  role = get_profile(identity_id=user_id).role
  size = 153600 if role == 'free_user' else -1

  # Render the upload form which will parse/submit the presigned POST
  return render_template('annotate.html', s3_post=presigned_post, size=size)


"""Fires off an annotation job
Accepts the S3 redirect GET request, parses it to extract 
required info, saves a job item to the database, and then
publishes a notification for the annotator service.
"""
@app.route('/annotate/job', methods=['GET'])
@authenticated
def create_annotation_job_request():
  # Parse redirect URL query parameters for S3 object info
  bucket_name = request.args.get('bucket')
  key_name = request.args.get('key')

  # Extract the job ID from the S3 key
  if not bucket_name or not key_name:
      return jsonify({'code': 500, 'error':'Cannot get bucket or key name.'})
      # internal_error()
  else:
      name, user, file_info = key_name.split('/')
      job_id, file_name = file_info.split('~') 

  # Persist job to database
  # Move your code here...
  data = {"job_id": job_id, "user_id": user, "input_file_name": file_name, "s3_inputs_bucket": bucket_name,
          "s3_key_input_file": key_name, "submit_time": int(time.time()), "job_status": "PENDING"}
  try:
      dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
      annotation_table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
      annotation_table.put_item(Item=data)
  except Exception as e:
      print(e)
  # Send message to request queue
  # Move your code here...
  try:
      sns = boto3.client('sns', region_name=app.config['AWS_REGION_NAME'])
      sns_response = sns.publish(TopicArn=app.config['AWS_SNS_JOB_REQUEST_TOPIC'], Message=json.dumps(data))
      print('===============================   Send notification to job request sqs   ===========================.')
  except Exception as e:
      raise e
  user_id = session['primary_identity']
  user_type = get_profile(identity_id=user_id).role
  # send notification to galcier
  if user_type == 'free_user':
    try:
      glacier_message = {'job_id': job_id, 'user_id': user, 'input_file_name': file_name,
                         's3_inputs_bucket': bucket_name, 's3_key_input_file': key_name}
      glacier_sns_response = sns.publish(TopicArn=app.config['AWS_SNS_GLACIER_TOPIC'], Message=json.dumps(glacier_message))
      print('===============================   Send notification to glacier sqs   ===========================.')
    except Exception as e:
      print(e)
  return render_template('annotate_confirm.html', job_id=job_id)


"""List all annotations for the user
"""
@app.route('/annotations', methods=['GET'])
@authenticated
def annotations_list():
  # Get list of annotations to display
  try:
    dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
    annotation_table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
    all_jobs = annotation_table.query(IndexName='user_id_index', KeyConditionExpression=Key('user_id').eq(session['primary_identity']), 
                                      Select='SPECIFIC_ATTRIBUTES', ProjectionExpression='job_id, submit_time, input_file_name, job_status')
  except Exception as e:
    print(e)
    return
  # set the submit time
  for job in all_jobs['Items']:
    time_elapsed = int(job['submit_time'])
    job['submit_time'] = datetime.fromtimestamp(time_elapsed).strftime('%Y-%m-%d %H:%M')
  return render_template('annotations.html', annotations=all_jobs['Items'])


"""Display details of a specific annotation job
"""
@app.route('/annotations/<id>', methods=['GET'])
@authenticated
def annotation_details(id):
  # get user information
  user_id = session['primary_identity']
  user_profile = get_profile(identity_id=user_id)
  user_type = user_profile.role
  try:
    dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
    annotation_table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
    all_jobs = annotation_table.query(KeyConditionExpression=Key('job_id').eq(id), Select='ALL_ATTRIBUTES')
    job = all_jobs['Items'][0]
    job['submit_time'] = datetime.fromtimestamp(int(job['submit_time'])).strftime('%Y-%m-%d %H:%M')
  except Exception as e:
    print(e)
    return
  # If not this user, not authorized to view this job.
  if job['user_id'] != session['primary_identity']:
    print('Not authorized to view this job.')
    forbidden()
    return
  try:
    s3 = boto3.client('s3', region_name=app.config['AWS_REGION_NAME'], config=Config(signature_version='s3v4'))
    input_ann = s3.generate_presigned_url(ClientMethod='get_object', 
                                          Params={'Bucket': app.config['AWS_S3_INPUTS_BUCKET'],
                                                  'Key': app.config['AWS_S3_KEY_PREFIX'] + session['primary_identity'] + '/' + str(id) + '~' + job['input_file_name']})
  except Exception as e:
    print(e)
    return
  if 'complete_time' in job:
    complete_time = float(job['complete_time'])
    job['complete_time'] = datetime.fromtimestamp(int(job['complete_time'])).strftime('%Y-%m-%d %H:%M')
  # use download_status flag to inform if the result can be downloaded.
  # if user is free user, check the time elasped after complete.
  if user_type == 'free_user':
    if job['job_status'] == 'COMPLETED':
      if time.time() - complete_time > float(app.config['FREE_USER_DATA_RETENTION']):  
        download_status = 'archived_to_glacier'
      else: 
        download_status = 'ready_to_download'     
      result_ann = s3.generate_presigned_url(ClientMethod='get_object', 
                                             Params={'Bucket': app.config['AWS_S3_RESULTS_BUCKET'],
                                                     'Key': app.config['AWS_S3_KEY_PREFIX'] + session['primary_identity'] + '/' + str(id) + '~' + job['input_file_name'].replace('.', '.annot.')})
    else:
      download_status = 'wait_for_complete'
      result_ann = None
  # premium user only need to check whether the job is finsished or not.
  elif user_type == 'premium_user':
    if job['job_status'] == 'COMPLETED':
      download_status = 'ready_to_download'
      result_ann = s3.generate_presigned_url(ClientMethod='get_object', 
                                             Params={'Bucket': app.config['AWS_S3_RESULTS_BUCKET'],
                                                     'Key': app.config['AWS_S3_KEY_PREFIX'] + session['primary_identity'] + '/' + str(id) + '~' + job['input_file_name'].replace('.', '.annot.')})
    else:
      download_status = 'wait_for_complete'
      result_ann = None
  return render_template('display_job.html', job=job, download_status=download_status, input_ann=input_ann, result_ann=result_ann)


"""Display the log file for an annotation job
"""
@app.route('/annotations/<id>/log', methods=['GET'])
@authenticated
def annotation_log(id):
  # query dynamodb to get the job which has the specified job id.
  try:
    dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
    annotation_table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
    job = annotation_table.query(KeyConditionExpression=Key('job_id').eq(id), Select='ALL_ATTRIBUTES')
  except Exception as e:
    print(e)
    return
  log_name = job['Items'][0]['input_file_name'] + '.count.log'
  # generate the log file for html page.
  try:
    s3 = boto3.client('s3', region_name=app.config['AWS_REGION_NAME'], config=Config(signature_version='s3v4'))
    log = s3.get_object(Bucket=app.config['AWS_S3_RESULTS_BUCKET'],
                        Key=app.config['AWS_S3_KEY_PREFIX'] + session['primary_identity'] + '/' + str(id) + '~' + log_name)
  except Exception as e:
    print(e)
    return
  return render_template('log.html', log=log)



"""Subscription management handler
"""
import stripe

@app.route('/subscribe', methods=['GET', 'POST'])
@authenticated
def subscribe():
  user_id = session['primary_identity']
  user_profile = get_profile(identity_id=user_id)
  if request.method == 'POST':
    # Extract the Stripe token from the submitted form.
    stripe_token = request.form.get('stripe_token')
    # Create a new Customer in Stripe
    stripe.api_key = app.config['STRIPE_SECRET_KEY']
    try:
      customer_response = stripe.Customer.create(description='Customer for %s' % (user_profile.email), source=stripe_token)
      # Subscribe the user to the premium plan
      subscription_response = stripe.Subscription.create(customer=customer_response['id'], items=[{'plan': app.config['SUBSCRIPTION_PLAN']}])
    except Exception as e:
      print(e)
      return  
    # Update the user’s profile in user database.
    update_profile(identity_id=session['primary_identity'], role='premium_user')
    # Initiate the archive restoration
    try:
      dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
      annotation_table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
      all_jobs = annotation_table.query(IndexName='user_id_index', KeyConditionExpression=Key('user_id').eq(user_id), Select='ALL_ATTRIBUTES')
      client_glacier = boto3.client('glacier', region_name=app.config['AWS_REGION_NAME'])
    except Exception as e:
      print(e)
      return
    for job in all_jobs['Items']:
      if 'archive_id' in job and job['archive_id']:
        # use while loop to guarntee that glacier initiate job successfully,
        # since there maybe capacity insufficient problem
        while True:
          try: 
            # SNSTopic is used to check is the job is complete or not.
            initiate_job_response = client_glacier.initiate_job(vaultName=app.config['AWS_GLACIER_VAULT'],
                                                                jobParameters={'Type': 'archive-retrieval', 'ArchiveId': job['archive_id'],
                                                                               'SNSTopic': app.config['AWS_SNS_ARCHIVE_RETRIEVE_TOPIC'], 'Tier': 'Expedited'})
            # initiate_job_response = client_glacier.initiate_job(vaultName=app.config['AWS_GLACIER_VAULT'],
            #                                                 jobParameters={'Type': 'archive-retrieval', 'ArchiveId': job['archive_id'], 'Description': 'My archive description',
            #                                                                'Tier': 'Expedited'})
            print('=======================Archive retrieve successfully.==========================')
            # do not use manual notification publish
            # job_id = job['job_id']
            # retrieve_id = initiate_job_response['jobId']
            # sns = boto3.client('sns', region_name=app.config['AWS_REGION_NAME'])
            # print(job_id)
            # print(retrieve_id)
            # message = json.dumps({'job_id': job_id, 'retrieve_id': retrieve_id})
            # sns_response = sns.publish(TopicArn=app.config['AWS_SNS_ARCHIVE_RETRIEVE_TOPIC'], Message=message)
            # print('Archive retrieve message sent successfully.')
          except Exception as e:
            print(e)
            continue
          # if all job are initiated, quit while loop.
          break
      elif 'complete_time' in job and (time.time() - float(job['complete_time'])) < float(app.config['FREE_USER_DATA_RETENTION']):
        try:
          sns = boto3.client('sns', region_name=app.config['AWS_REGION_NAME'])
          sns_response = sns.publish(TopicArn=app.config['AWS_SNS_GLACIER_TOPIC'], Message=json.dumps({'job_id': job['job_id'], 'canceled_archive': job['job_id']}))
        except Exception as e:
          print(e)
          return
    return render_template('subscribe_confirm.html', stripe_id=customer_response['id'])    
  else:
    return render_template('subscribe.html')

# cancel the subscription
@app.route('/cancel_subscribe', methods=['GET'])
@authenticated
def cancel_subscribe():
  update_profile(identity_id=session['primary_identity'], role="free_user")
  return render_template('cancel_subscribe.html')


"""DO NOT CHANGE CODE BELOW THIS LINE
*******************************************************************************
"""

"""Home page
"""
@app.route('/', methods=['GET'])
def home():
  return render_template('home.html')

"""Login page; send user to Globus Auth
"""
@app.route('/login', methods=['GET'])
def login():
  app.logger.info('Login attempted from IP {0}'.format(request.remote_addr))
  # If user requested a specific page, save it to session for redirect after authentication
  if (request.args.get('next')):
    session['next'] = request.args.get('next')
  return redirect(url_for('authcallback'))

"""404 error handler, 404 Not Found
"""
@app.errorhandler(404)
def page_not_found(e):
  return render_template('error.html', 
    title='Page not found', alert_level='warning',
    message="The page you tried to reach does not exist. Please check the URL and try again."), 404

"""403 error handler, 403 Forbidden
"""
@app.errorhandler(403)
def forbidden(e):
  return render_template('error.html',
    title='Not authorized', alert_level='danger',
    message="You are not authorized to access this page. If you think you deserve to be granted access, please contact the supreme leader of the mutating genome revolutionary party."), 403

"""405 error handler, 405 Method Not Allowed
"""
@app.errorhandler(405)
def not_allowed(e):
  return render_template('error.html',
    title='Not allowed', alert_level='warning',
    message="You attempted an operation that's not allowed; get your act together, hacker!"), 405

"""500 error handler, 500 Internal Server Error
"""
@app.errorhandler(500)
def internal_error(error):
  return render_template('error.html',
    title='Server error', alert_level='danger',
    message="The server encountered an error and could not process your request."), 500

### EOF
