from ckan.lib.mailer import mail_recipient, MailerException
from ckan.common import config
import logging
from flask import render_template_string
from ckan.plugins.toolkit import h
import ckan.plugins.toolkit as tk
from ckan.common import _

def extract_request_data(request):
    """
    Extracts relevant data from the request for email purposes.
    """
    return {
        'name': request.values.get('name'),
        'email': request.values.get('email'),
    }

def generate_new_collection_admin_email_body(request):
    data = {
        'name': request.values.get('name'),
        'email': request.values.get('email'),
        'collection_full_name': request.values.get('collection_full_name'),
        'collection_short_name': request.values.get('collection_short_name'),
        'is_culturally_sensitive': request.values.get('is_culturally_sensitive'),
        'description': request.values.get('description')
    }    
    email_body_template = """
    Dear AuScope Sample Repository admin,

    A new collection request has been submitted. Below are the details of the request:

    Contact Name: {{ data.name }}
    Contact Email: {{ data.email }}
    
    Collection Details:
    - Full Name: {{ data.collection_full_name }}
    - Short Name: {{ data.collection_short_name }}
    - Culturally Sensitive: {{ data.is_culturally_sensitive}}
    
    Description of the Collection:
    {{ data.description }}

    Please take the necessary steps to process this request.

    Thank you.

    """
    return render_template_string(email_body_template, data=data)

def send_new_collection_requester_confirmation_email(request):
    """
    Sends a confirmation email to the requester for a new collection request.
    """
    collection_full_name= request.values.get('collection_full_name')
    recipient_email= request.values.get('email')
    recipient_name= request.values.get('name')
    body = generate_new_collection_requester_email_body(request)
    subject = f'AuScope Sample Repository - Request to create collection "{collection_full_name}" has been submitted'
    mail_recipient(recipient_name, recipient_email, subject, body)

def generate_new_collection_requester_email_body(request):
    """
    Generates the email body for the requester.
    """
    data = {
        'name': request.values.get('name'),
        'email': request.values.get('email'),
        'collection_full_name': request.values.get('collection_full_name'),
        'collection_short_name': request.values.get('collection_short_name'),
        'is_culturally_sensitive': request.values.get('is_culturally_sensitive'),
        'description': request.values.get('description')
    }    
        
    site_title = config.get('ckan.site_title')
    site_url = config.get('ckan.site_url')
    return f"""
Dear {data['name']},

Thank you for submitting a new request to create a new collection. Below are the details of the request:

Contact Name: {data['name']}
Contact Email: {data['email']}

Collection Details:
- Full Name: {data['collection_full_name']}
- Short Name: {data['collection_short_name']}
- Culturally Sensitive: {data['is_culturally_sensitive']}

Description of the Collection:
{data['description']}

Our admin will review and contact you with regards to creating your collection.

Kind Regards,
AuScope Sample Repository
--
Message sent by {site_title} ({site_url})
    """

def generate_join_collection_admin_email_body(request,org_id,org_name):
    data = {
        'name': request.values.get('name'),
        'email': request.values.get('email'),
        'description': request.values.get('description'),
        'collection_id': org_id,
        'collection_name': org_name
    }

    email_body_template = """
    Dear AuScope Sample Repository admin,

    A new request to join the collection has been submitted. Below are the details of the request:

    Contact Name: {{ data.name }}
    Contact Email: {{ data.email }}

    Description of Request:
    {{ data.description }}

    Collection Details:
    - Collection ID: {{ data.collection_id }}
    - Collection Name: {{ data.collection_name }}

    Please take the necessary steps to process this request.

    Thank you.
    
    """
    return render_template_string(email_body_template, data=data)

def send_join_collection_requester_confirmation_email(request, organization):
    """
    Mail a confirmation to the user to join a collection and notify the contact person.
    """
    logger = logging.getLogger(__name__)

    org_name = organization['name']
    contact_email = organization['contact_email']
    contact_name = organization['contact_name']
    
    recipient_email = request.values.get('email')
    recipient_name = request.values.get('name')
    
    if not recipient_email or not recipient_name:
        logger.error('Recipient email or name is missing.')
        return

    subject = f'AuScope Sample Repository - Request to join the collection "{org_name}" has been submitted'

    try:
        requester_body = generate_join_collection_requester_email_body(request, organization)
        mail_recipient(recipient_name, recipient_email, subject, requester_body)
        logger.info(f'Email sent to requester {recipient_email}')

        if contact_email and contact_email != recipient_email:
            contact_body = generate_join_collection_contact_email_body(request, organization)
            mail_recipient(contact_name, contact_email, subject, contact_body)
            logger.info(f'Notification email sent to contact {contact_email}')
        else:
            logger.info('Contact email is the same as requester email, no separate email sent to contact.')

    except MailerException as e:
        logger.error(f'Error during email sending: {e}')
    except Exception as e:
        logger.error(f'Unexpected error during email sending: {e}')

def generate_join_collection_requester_email_body(request,organization):
    """
    Generates the email body for the requester.
    """
    org_id= organization['id']
    org_name = organization['name']

    data = {
        'name': request.values.get('name'),
        'email': request.values.get('email'),
        'description': request.values.get('description'),
        'collection_id': org_id,
        'collection_name': org_name
    }
        
    site_title = config.get('ckan.site_title')
    site_url = config.get('ckan.site_url')
    return f"""
Dear {data['name']},

Thank you for submitting a new request to join the collection. Below are the details of the request:

Contact Name: {data['name']}
Contact Email: {data['email']}

Description of Request:
{data['description']}

Collection Details:
- Collection ID: { data['collection_id'] }
- Collection Name: { data['collection_name'] }

Our admin will review and contact you with regards to joining the collection.

Kind Regards,
AuScope Sample Repository
--
Message sent by {site_title} ({site_url})
    """

def generate_join_collection_contact_email_body(request, organization):
    """
    Generates the email body for the contact person to notify about a join request.
    """
    data = extract_request_data(request)
    org_name = organization['name']

    return f"""
Dear {organization['contact_name']},

A new request to join the collection "{org_name}" has been submitted. Below are the details of the request:

Requester Name: {data['name']}
Requester Email: {data['email']}

Please note that the admin will take necessary steps to process this request.

Thank you,
AuScope Sample Repository
--
Message sent by {config.get('ckan.site_title')} ({config.get('ckan.site_url')})
    """

def organization_create_notify_email(data_dict):
    collection_full_name = data_dict.get('title')
    recipient_email = data_dict.get('contact_email')
    recipient_name = data_dict.get('contact_name')
    site_title = config.get('ckan.site_title')
    site_url = config.get('ckan.site_url')

    subject = f'Collection Created: {collection_full_name}'
    body = f"""
    Dear {recipient_name},

    The collection '{collection_full_name}' has been successfully created.

    Kind Regards,
    AuScope Sample Repository
    --
    Message sent by {site_title} ({site_url})
    """       
    mail_recipient(recipient_name, recipient_email, subject, body)

def organization_delete_notify_email(organization):
    collection_full_name = organization.get('title')
    recipient_email = organization.get('contact_email')
    recipient_name = organization.get('contact_name')
    site_title = config.get('ckan.site_title')
    site_url = config.get('ckan.site_url')

    subject = f'Collection Deleted: {collection_full_name}'
    body = f"""
    Dear {recipient_name},

    The collection '{collection_full_name}' has been successfully deleted.

    Kind Regards,
    AuScope Sample Repository
    --
    Message sent by {site_title} ({site_url})
    """
    mail_recipient(recipient_name, recipient_email, subject, body)

def organization_member_create_notify_email(context, data_dict):
    """
    Notify the user and the collection contact when a new member is added to the collection.
    """
    logger = logging.getLogger(__name__)

    try:
        collection_id = data_dict.get('id')
        user_id = data_dict.get('username')

        user_obj = tk.get_action('user_show')(context, {'id': user_id})
        collection_obj = tk.get_action('organization_show')(context, {'id': collection_id})

        recipient_email = user_obj.get('email')
        recipient_name = user_obj.get('display_name') or user_obj.get('name')
        collection_name = collection_obj.get('title')
        site_title = config.get('ckan.site_title')
        site_url = config.get('ckan.site_url')

        contact_email = collection_obj.get('contact_email')
        contact_name = collection_obj.get('contact_name') or 'Collection Contact'

        subject = f'You have been added to the collection: {collection_name}'

        if not recipient_email or not recipient_name:
            logger.error('Recipient email or name is missing.')
            h.flash_error(_('The member has been added to the collection but there was an error preparing the notification email.'), 'error')
            return

        try:
            recipient_body = generate_new_member_email_body(recipient_name, collection_name, site_title, site_url)
            mail_recipient(recipient_name, recipient_email, subject, recipient_body)
            logger.info(f'Notification email sent to new member {recipient_email}')

            if contact_email and contact_email != recipient_email:
                contact_body = generate_contact_notification_email_body(contact_name, recipient_name, collection_name, site_title, site_url)
                mail_recipient(contact_name, contact_email, subject, contact_body)
                logger.info(f'Notification email sent to contact {contact_email}')
            else:
                logger.info('Contact email is the same as the new member email, no separate email sent to contact.')

            h.flash_success(_('The member has been added to the collection and the notification email has been sent successfully.'))

        except MailerException as e:
            logger.error(f'Error during email sending: {e}')
            h.flash_error(_('The member has been added to the collection but there was an error sending the notification email. Please check the email configuration.'), 'error')

    except Exception as e:
        logger.error(f'Unexpected error during email sending: {e}')
        h.flash_error(_('The member has been added to the collection but there was an unexpected error sending the notification email. Please check the email configuration.'), 'error')

def generate_new_member_email_body(recipient_name, collection_name, site_title, site_url):
    """
    Generates the email body for the new member added to the collection.
    """
    return f"""
Dear {recipient_name},

You have been successfully added to the collection '{collection_name}'.

Kind Regards,
AuScope Sample Repository
--
Message sent by {site_title} ({site_url})
    """

def generate_contact_notification_email_body(contact_name, recipient_name, collection_name, site_title, site_url):
    """
    Generates the email body to notify the contact about the new member.
    """
    return f"""
Dear {contact_name},

{recipient_name} has been successfully added to the collection '{collection_name}'.

Kind Regards,
AuScope Sample Repository
--
Message sent by {site_title} ({site_url})
    """