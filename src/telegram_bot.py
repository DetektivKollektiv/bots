import os
from telegram import *
from telegram.ext import *
import logging
from time import sleep
from functools import wraps
import requests
import json
import boto3
import base64
from botocore.exceptions import ClientError

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

GDPR, TYPE, CONTENT, ADD_INFO, CONTACT, FREQUENCY, CHANNEL, SUBMIT = range(8)

# For API calls and web links (e.g. to the archive)
API_PREFIX = "dev."

try:
    SECRET_NAME = "telegram_bot_token_{}".format(os.environ['STAGE'])
    if os.environ['STAGE'] == "prod":
        API_PREFIX = ""
    else:
        API_PREFIX = "{}.".format(os.environ['STAGE'])
except KeyError:
    # if environment variable is not set (e.g. in local debugging): use local dev bot token
    SECRET_NAME = "telegram_bot_token_local_dev"


class TelegramTokenError(Exception):
    pass

def get_telegram_token():
    """Gets the telegram bot token for the respective stage (dev/qa/prod) from the secrets manager.
    Parameters
    ----------
    is_test: boolean
        If this method is called from a test
    SECRET_NAME: string
        The name of the telegram bot token in the secrets manager
    """

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name='eu-central-1'
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=SECRET_NAME
        )

        print(get_secret_value_response)

        # Decrypts secret using the associated KMS CMK.
        secret = get_secret_value_response['SecretString']
        telegram_bot_token = json.loads(secret)[SECRET_NAME]

        return telegram_bot_token

    except ClientError as e:
        logging.exception("Could not get telegram bot token from the secrets manager. Secrets manager error: {}".format(
            e.response['Error']['Code']))
        raise TelegramTokenError


def typing(original_function=None, seconds=None):
    """Makes the bot look like its typing To be used as a decorator, e.g. "@typing" or "@typing(seconds=2)". 

    Parameters
    ----------
    seconds: int, optional
        How long the bot should be typing (in seconds). Default: 0.75
    """

    def _decorate(function):

        @wraps(function)
        def wrapped_function(update, context, *args, **kwargs):
            context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)
            if seconds: 
                sleep(seconds)
            else: 
                sleep(0.75)
            return function(update, context,  *args, **kwargs)

        return wrapped_function

    if original_function:
        return _decorate(original_function)

    return _decorate


@typing
def start(update, context):
        """Send message on `/start`."""

        # Get user that sent /start and log his name
        user = update.message.from_user
        logger.info("User {} started a new conversation. Metadata: \n{}".format(user.username, update))

        # Clear all previous user data
        context.user_data.clear()

        # Build InlineKeyboard where each button has a displayed text
        # and a string as callback_data
        # The keyboard is a list of button rows, where each row is in turn
        # a list (hence `[[...]]`).
        keyboard = [
            [InlineKeyboardButton("ja", callback_data="ja"),
            InlineKeyboardButton("nein", callback_data="nein")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        hello_text = """
        Hi {}, hier ist Derrick - die tüchtige Assistenz des DetektivKollektivs. Danke, dass du dich an uns wendest! 🤩
        \nBevor du einen Fall an unsere Detektiv*innen weiterleiten kannst, müsstest du erst unserer <a href='https://{}detective-collective.org/data-privacy'>Datenschutzerklärung</a> zustimmen.
        """
        update.message.reply_text(hello_text.format(user.first_name, API_PREFIX), parse_mode=ParseMode.HTML)
        # Send message with text and appended InlineKeyboard
        update.message.reply_text(
            "Bist du mit der Datenschutzerklärung einverstanden?",
            reply_markup=reply_markup
        )
        # Tell ConversationHandler that we're in state `GDPR` now
        return GDPR


@typing
def welcome_back(update, context):
        """Send message on `/start`."""

        # Get user that sent /start and log his name
        user = update.message.from_user
        logger.info("User {} started a new conversation. Metadata: \n{}".format(user.username, update))

        # Clear all previous user data
        context.user_data.clear()

        # Build InlineKeyboard where each button has a displayed text
        # and a string as callback_data
        # The keyboard is a list of button rows, where each row is in turn
        # a list (hence `[[...]]`).
        keyboard = [
            [InlineKeyboardButton("ja", callback_data="ja"),
            InlineKeyboardButton("nein", callback_data="nein")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        hello_text = """
        Hi {}! 👋 Bevor wir deinen Fall annehmen können, musst du wie immer unserer <a href='https://{}detective-collective.org/data-privacy'>Datenschutzerklärung</a> zustimmen.
        """
        update.message.reply_text(hello_text.format(user.first_name, API_PREFIX), parse_mode=ParseMode.HTML)
        # Send message with text and appended InlineKeyboard
        update.message.reply_text(
            "Bist du mit der Datenschutzerklärung einverstanden?",
            reply_markup=reply_markup
        )
        # Tell ConversationHandler that we're in state `GDPR` now
        return GDPR


@typing
def gdpr_accepted(update, context):
    """Next step: Ask user for item type"""

    query = update.callback_query
    user =  query.from_user

    keyboard = [
            [InlineKeyboardButton("Textnachricht ✏️", callback_data="claim"),
            InlineKeyboardButton("Link zu Artikel 📰", callback_data="article")]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
        
    user.send_message(
        "Super, dann können wir ja loslegen! 🙌 \n\nHandelt es sich bei deinem Fall um eine reine Textnachricht bzw. Aussage oder um einen Link zu einem Artikel?",
        reply_markup=reply_markup
    )

    return TYPE


@typing
def gdpr_denied(update, context):
    """Returns `ConversationHandler.END`, which tells the
    ConversationHandler that the conversation is over"""
    query = update.callback_query
    user = query.from_user
    user.send_message("Alles klar. Schau doch mal in unser Archiv auf https://{}detective-collective.org/archive, vielleicht ist Dein Fall ja schon dabei!".format(API_PREFIX))
    return ConversationHandler.END


@typing
def ask_content(update, context):

    query = update.callback_query
    user =  query.from_user
    context.user_data["type"] = query.data
    type = context.user_data["type"]

    if type == "claim":
        user.send_message("Okay. Bitte gib jetzt die Nachricht ein, die du überprüfen lassen möchtest. Du kannst die Nachricht auch an mich weiterleiten.")
    else:
        user.send_message("Okay. Bitte gib jetzt den Link (URL) zu dem Artikel ein, den du überprüfen lassen möchtest.")     

    return CONTENT


@typing
def ask_additional_info(update, context):

    user = update.message.from_user
    context.user_data["content"] = update.message.text
    context.user_data["give_add_info"] = False
    logger.info("User %s wants to submit new item: %s", user.username, context.user_data["content"])

    keyboard = [
            [InlineKeyboardButton("ja", callback_data="ja"),
            InlineKeyboardButton("nein", callback_data="nein")]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
        
    update.message.reply_text(
        "Möchtest du uns noch ein paar zusätzliche Informationen zu deinem Fall geben?",
        reply_markup=reply_markup
    )

    return ADD_INFO


@typing
def ask_contact(update, context):

    query = update.callback_query
    user =  query.from_user
    logger.info("User %s wants to provide contact.", user.username)
    
    context.user_data["give_add_info"] = True

    keyboard = [
            [InlineKeyboardButton("Familie / enge Freunde", callback_data="family"),
            InlineKeyboardButton("Bekannte", callback_data="acquaintance")],
            [InlineKeyboardButton("Fremde", callback_data="stranger"),
            InlineKeyboardButton("Sonstiges", callback_data="other")],
            [InlineKeyboardButton("überspringen ⏩", callback_data="skip")]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    user.send_message("Alles klar! Wie hat dich die Information erreicht?",reply_markup=reply_markup)      

    return CONTACT


@typing
def ask_frequency(update, context):

    query = update.callback_query
    user =  query.from_user
    context.user_data["contact"] = query.data
    logger.info("User %s provided contact: %s", user.username, context.user_data["contact"])
    logger.info("User %s wants to provide frequency.", user.username)

    keyboard = [
            [InlineKeyboardButton("1", callback_data="1"),
            InlineKeyboardButton("2", callback_data="2"),
            InlineKeyboardButton("3", callback_data="3")],
            [InlineKeyboardButton("4", callback_data="4"),
            InlineKeyboardButton("5", callback_data="5"),
            InlineKeyboardButton("6+", callback_data="6+")],
            [InlineKeyboardButton("⏪ zurück", callback_data="back"),
            InlineKeyboardButton("überspringen ⏩", callback_data="skip")]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    user.send_message("Okay. Wie oft hat dich die Information insgesamt erreicht?",reply_markup=reply_markup)        

    return FREQUENCY


@typing
def ask_channel(update, context):

    query = update.callback_query
    user =  query.from_user
    context.user_data["frequency"] = query.data
    logger.info("User %s provided frequency: %s", user.username, context.user_data["frequency"])
    logger.info("User %s wants to provide channel.", user.username)

    keyboard = [
            [InlineKeyboardButton("SMS oder Messenger (z.B. WhatsApp) 📱", callback_data="messenger")],
            [InlineKeyboardButton("soziale Medien (z.B. Facebook, Twitter) 💬", callback_data="social_media")],
            [InlineKeyboardButton("Videoplattform (z.B. Youtube) ▶️", callback_data="video_platform")],
            [InlineKeyboardButton("mündlich 🗣", callback_data="orally"),
            InlineKeyboardButton("Internet allgemein 🖥", callback_data="internet")],
            [InlineKeyboardButton("Fernsehen 📺", callback_data="tv"),
            InlineKeyboardButton("Sonstiges", callback_data="other")],
            [InlineKeyboardButton("⏪ zurück", callback_data="back"),
            InlineKeyboardButton("überspringen ⏩", callback_data="skip")]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    user.send_message("Okay. Wo hat dich die Information als Erstes erreicht?",reply_markup=reply_markup)        

    return CHANNEL


@typing
def confirm_submit_item(update, context):
    query = update.callback_query
    user = query.from_user
    if query.data != "nein":
        context.user_data["channel"] = query.data
        logger.info("User %s provided channel: %s", user.username, context.user_data["channel"])

    if context.user_data["give_add_info"]:
        keyboard = [
        [InlineKeyboardButton("Ja, Fall einreichen! ✔️", callback_data="submit")],
        [InlineKeyboardButton("⏪ zurück", callback_data="back"),
        InlineKeyboardButton("abbrechen 🚫", callback_data="cancel")]
        ]
    else:
        keyboard = [
        [InlineKeyboardButton("Ja, Fall einreichen! ✔️", callback_data="submit")],
        [InlineKeyboardButton("abbrechen 🚫", callback_data="cancel")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    user.send_message("Okay! Möchtest du den Fall jetzt einreichen?",reply_markup=reply_markup)        

    return SUBMIT


@typing
def submit_item(update, context):
    query = update.callback_query
    user =  query.from_user
    logger.info("User %s wants to submit item.", user.username)

    # Prepare new item submission
    new_submission = context.user_data
    print(new_submission)
    to_remove = []
    for key in new_submission:
        if new_submission[key] == "skip":
            to_remove.append(key)
    for key in to_remove:
        new_submission.pop(key)
    # TODO: set telegram_id (requires model to be changed)
    new_submission["telegram_id"] = user.id
    print(new_submission)

    # Call API endpoint /item_submission
    api_url = "https://api.{}detective-collective.org/item_submission".format(API_PREFIX)
    r = requests.post(api_url, data = json.dumps(new_submission))
    
    logger.info("New item submitted by user {}. Response code: {}. New item created: {}. Body: {}".format(user.username, r.status_code, r.headers["new-item-created"], r.text))

    query.from_user.send_message("Vielen Dank, dein Fall wurde nun eingereicht! 🥳 Wir melden uns bei dir, sobald unsere Detektiv*innen deinen Fall gelöst haben.")
    return ConversationHandler.END


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(get_telegram_token(), use_context=True)

    # Get the dispatcher to register handlers
    # TODO: replace dev with env variable
    dp = updater.dispatcher

    # Setup conversation handler with the states FIRST and SECOND
    # Use the pattern parameter to pass CallbackQueries with specific
    # data pattern to the corresponding handlers.
    # ^ means "start of line/string"
    # $ means "end of line/string"
    # So ^ABC$ will only allow 'ABC'
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start, pass_user_data=True), MessageHandler(Filters.text, welcome_back)],
        # entry_points=[CommandHandler('start', start, pass_user_data=True)],
        states={
            GDPR: [CallbackQueryHandler(gdpr_accepted, pattern='^ja$'),
                    CallbackQueryHandler(gdpr_denied, pattern='^nein$')],
            TYPE: [CallbackQueryHandler(ask_content, pattern='^claim$|^article$')],
            CONTENT: [MessageHandler(Filters.text, ask_additional_info)],
            ADD_INFO: [CallbackQueryHandler(ask_contact, pattern='^ja$'),
                    CallbackQueryHandler(confirm_submit_item, pattern='^nein$')],
            CONTACT: [CallbackQueryHandler(ask_frequency, pattern='^family$'),
                    CallbackQueryHandler(ask_frequency, pattern='^acquaintance$'),
                    CallbackQueryHandler(ask_frequency, pattern='^stranger$'),
                    CallbackQueryHandler(ask_frequency, pattern='^other$'),
                    CallbackQueryHandler(ask_frequency, pattern='^skip$')],
            FREQUENCY: [CallbackQueryHandler(ask_contact, pattern='^back$'),
                    CallbackQueryHandler(ask_channel, pattern='^1$'),
                    CallbackQueryHandler(ask_channel, pattern='^2$'),
                    CallbackQueryHandler(ask_channel, pattern='^3$'),
                    CallbackQueryHandler(ask_channel, pattern='^4$'),
                    CallbackQueryHandler(ask_channel, pattern='^5$'),
                    CallbackQueryHandler(ask_channel, pattern='^6\+$'),
                    CallbackQueryHandler(ask_channel, pattern='^skip$')],
            CHANNEL: [CallbackQueryHandler(ask_frequency, pattern='^back$'),
                    CallbackQueryHandler(confirm_submit_item, pattern='^messenger$'),
                    CallbackQueryHandler(confirm_submit_item, pattern='^social_media$'),
                    CallbackQueryHandler(confirm_submit_item, pattern='^video_platform$'),
                    CallbackQueryHandler(confirm_submit_item, pattern='^orally$'),
                    CallbackQueryHandler(confirm_submit_item, pattern='^internet$'),
                    CallbackQueryHandler(confirm_submit_item, pattern='^tv$'),
                    CallbackQueryHandler(confirm_submit_item, pattern='^other$'),
                    CallbackQueryHandler(confirm_submit_item, pattern='^skip$')],
            SUBMIT: [CallbackQueryHandler(ask_channel, pattern='^back$'),
                    CallbackQueryHandler(submit_item, pattern='^submit$'),
                    CallbackQueryHandler(gdpr_denied, pattern='^cancel$')],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # Add ConversationHandler to dispatcher that will be used for handling
    # updates
    dp.add_handler(conv_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()