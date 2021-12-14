import os
import sys
import time
import optparse
import flask
import logging
from logging.handlers import RotatingFileHandler

from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

from selenium import webdriver

from slackclient import SlackClient

sc = SlackClient(os.environ['SLACK_TOKEN'])

app = flask.Flask(__name__)

formatter = logging.Formatter('%(asctime)s - %(levelname)10s - %(module)15s:%(funcName)30s:%(lineno)5s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)
fileHandler = RotatingFileHandler('X:\\Scripts\\Logs\\abacus.log', maxBytes=1024 * 1024 * 1, backupCount=1)
# fileHandler = RotatingFileHandler('/app/logs/abacus.log', maxBytes=1024 * 1024 * 1, backupCount=1)
logger.setLevel(os.environ['LOG_LEVEL'].upper())
logging.getLogger("requests").setLevel(logging.WARNING)
fileHandler.setFormatter(formatter)
logger.addHandler(fileHandler)


def send_message(text):
	result = sc.api_call("chat.postMessage", channel=os.environ['SLACK_CHANNEL'], text=text)
	return result


class Abacus(object):

	def __init__(self):
		self.status = None
		self.browser = None

	def start_browser(self):
		option = webdriver.ChromeOptions()
		try:
			if os.environ['DOCKER']:
				option.add_argument('--no-sandbox')
		except KeyError:
			pass

		chrome_path = os.path.join(os.getcwd(), "chrome")
		option.add_argument("--user-data-dir="+chrome_path)

		option.add_argument("enable-automation")
		# option.add_argument("--headless")
		# option.add_argument("--window-size=1920,1080");
		# option.add_argument("--disable-extensions");
		# option.add_argument("--dns-prefetch-disable");
		# option.add_argument("--disable-gpu");
		# option.setPageLoadStrategy(PageLoadStrategy.NORMAL);
		
		s = Service(ChromeDriverManager().install())
		driver = webdriver.Chrome(service=s, options=option)
		driver.maximize_window()
		self.browser = driver
		logger.info("Chrome Successfully Started")

	def login(self):
		if self.browser is None:
			self.start_browser()
		self.browser.get("https://abacus.myisolved.com/UserLogin.aspx")
		self.browser.maximize_window()
		self.browser.implicitly_wait(30)

		try:
			logger.debug("Entering Username")
			self.browser.find_element(By.ID, "ctl00_DefaultContent_Login1_UserName").send_keys(os.environ['USERNAME'], Keys.ENTER)
			logger.debug("Entering Password")
			self.browser.find_element(By.ID, "ctl00_DefaultContent_Login1_Password").send_keys(os.environ['PASSWORD'], Keys.ENTER)
		except Exception as e:
			logger.error('Error on line {} {} {}'.format(sys.exc_info()[-1].tb_lineno, type(e).__name__, e))

		try:
			self.browser.find_element(By.XPATH, '//*[@id="ctl00_DefaultContent_AuthCodeSMSSelect"]').click()
			self.browser.find_element(By.XPATH, '//*[@id="ctl00_DefaultContent_GetAuthCodeButton"]').click()
			logger.info("2FA Sent")
			result = send_message("New Abacus Request")
			last_result = None

			while True:
				try:
					logger.info("Waiting for 2FA Response...")
					time.sleep(5)
					last_result = \
						sc.api_call("conversations.replies", ts=result['ts'], channel=os.environ['SLACK_CHANNEL'])[
							'messages']
					reply_count = last_result[0]['reply_count']
					logger.info("2FA Code Received")
				except KeyError:
					reply_count = 0
				if reply_count != 0:
					break

			self.browser.find_element(By.ID, 'ctl00_DefaultContent_AuthCodeTextBox').send_keys(last_result[-1]['text'], Keys.RETURN)
		except NoSuchElementException:
			pass
		except WebDriverException:
			self.browser = None
			self.login()
		except Exception as e:
			logger.error('Error on line {} {} {}'.format(sys.exc_info()[-1].tb_lineno, type(e).__name__, e))

		try:
			header = self.browser.find_element(By.XPATH, '//*[@id="ctl00_DefaultContent_EmployeeLandingPageView"]/div[1]').text
			if 'Welcome back' in header:
				logger.info("Login Successful")
				time.sleep(5)
				self.update_status()
		except Exception as e:
			logger.error('Error on line {} {} {}'.format(sys.exc_info()[-1].tb_lineno, type(e).__name__, e))
			logger.error(self.status)

	def update_status(self):
		try:
			logger.debug("Updating Status")
			current_status = None
			self.browser.find_element(By.XPATH, '//*[@id="SelfServicePunchDropDown"]').click()
			while current_status is None:
				try:
					current_status = self.browser.find_element(By.XPATH, '//*[@id="SelfServicePunchDropDown"]/ul/li[8]').text.split(":")[1].strip().upper()
				except IndexError:
					self.browser.find_element(By.XPATH, '//*[@id="SelfServicePunchDropDown"]').click()
					current_status = None
				except Exception as e:
					logger.error('Error on line {} {} {}'.format(sys.exc_info()[-1].tb_lineno, type(e).__name__, e))
					current_status = None
					break

			self.status = current_status
		except Exception as e:
			if self.browser is None:
				logger.error("Failed Updating Status, Try Logging In")
			else:
				logger.error('Error on line {} {} {}'.format(sys.exc_info()[-1].tb_lineno, type(e).__name__, e))

	def quick_punch(self):
		try:
			current_status = self.status
			logger.debug("Submitting Quick Punch")
			
			for attempt in range(5):
				self.browser.find_element(By.XPATH, '//*[@id="SelfServiceMenu_QuickPunch"]').click()
				self.update_status()
				new_status = self.status
				if current_status != new_status:
					logger.info("Punch Submitted After %s attempts" % attempt)
					send_message("Abacus Successfully Punched. Status is now %s" % self.status)
					break
			else:
				logger.error("Status Not Changed, Trying Again")
				send_message("Abacus Punch Failed. Verify Punch")
				
		except Exception as e:
			if self.browser is None:
				logger.error("Failed Submitting Punch, Try Logging In")
			else:
				logger.error('Error on line {} {} {}'.format(sys.exc_info()[-1].tb_lineno, type(e).__name__, e))

	def set_status(self, status):
		aba.update_status()
		if self.status.upper() != status.upper():
			logger.debug("Applying Quick Punch")
			self.quick_punch()
		else:
			logger.info("Status Already Set to %s" % self.status.upper())


@app.route('/')
def index():
	try:
		status_code = flask.Response(status=201)
		return status_code
	except KeyError:
		flask.abort(404)


if __name__ == "__main__":
	parser = optparse.OptionParser()
	parser.add_option('-i', '--initialize', action="store_const", const=True, dest="initialize")
	parser.add_option('-s', '--set', action="store_const", const=True, dest="set_status")
	options, args = parser.parse_args()

	if options.set_status:
		aba = Abacus()
		aba.login()
		aba.set_status(args[0])
		aba.browser.close()
		aba = None
	# if options.initialize:
	# 	logger.info("Starting Server")
	# 	app.run(host='0.0.0.0', port=8800)
