import json
import logging
import sys
import time
import httpx
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
import asyncio
from pathlib import Path
import os

from dotenv import load_dotenv
load_dotenv()

CC_CCV = os.getenv('CC_CCV')
BB_USERNAME = os.getenv('BB_USERNAME')
BB_PASSWORD = os.getenv('BB_PASSWORD')
DEFAULT_REFRESH_INTERVAL_SECONDS = 30
REFRESH_INTERVAL_SECONDS = os.getenv('REFRESH_INTERVAL_SECONDS', DEFAULT_REFRESH_INTERVAL_SECONDS)


class BBBrowserClient:

    def __init__(self):
        if BB_USERNAME is None or BB_PASSWORD is None:
            raise ValueError('Credentials not defined!')
        fireFoxOptions = webdriver.FirefoxOptions()
        fireFoxOptions.headless = True
        fireFoxOptions.set_preference("geo.enabled", False)
        self.driver = webdriver.Firefox(options=fireFoxOptions)
        self.cookies = None

    def login(self):

        self.driver.get('https://www.bestbuy.com')
        self.driver.get('https://www.bestbuy.com/identity/global/signin')

        username_field = self.try_get_element_by_xpath('/html/body/div[1]/div/section/main/div[1]/div/div/div/div/form/div[1]/div/input')

        username_field.send_keys(BB_USERNAME)

        password_field = self.try_get_element_by_xpath('/html/body/div[1]/div/section/main/div[1]/div/div/div/div/form/div[2]/div/input')

        password_field.send_keys(BB_PASSWORD)

        login_button = self.try_get_element_by_xpath('/html/body/div[1]/div/section/main/div[1]/div/div/div/div/form/div[4]/button')
        login_button.click()

        time.sleep(5)

        self.cookies = self.driver.get_cookies()

        self.driver.close()

    def try_get_element_by_xpath(self, xpath):

        element = WebDriverWait(self.driver, 5).until(
            expected_conditions.element_to_be_clickable((By.XPATH, xpath))
        )
        return element


class BBApiClient:

    BB_BASE_URL = 'https://www.bestbuy.com'
    USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def close(self):
        await self.client.aclose()

    async def request(self, **kwargs):
        headers = {
                'user-agent': self.USER_AGENT
            }
        if 'headers' in kwargs:
            kwargs['headers'].update(headers)

        response = await self.client.request(
            **kwargs
        )

        if not response.status_code == 200:
            url = kwargs['url']
            method = kwargs['method']
            status = response.status_code
            response_text = response.text
            request_data = json.dumps(kwargs['json']) if 'json' in kwargs else None
            raise BBApiException(f'Request {method} {url} failed with status {status}\n\tRequest data: {request_data}\n\tResponse data: {response_text}')
        return response

    async def get(self, resource, **kwargs):
        return await self.request(
            method='GET',
            url=self.BB_BASE_URL + resource,
            **kwargs
        )

    async def post(self, resource, json, **kwargs):
        return await self.request(
            method='POST',
            url=self.BB_BASE_URL + resource,
            json=json,
            **kwargs
        )

    async def put(self, resource, json, **kwargs):
        return await self.request(
            method='PUT',
            url=self.BB_BASE_URL + resource,
            json=json,
            **kwargs
        )

    async def patch(self, resource, json, **kwargs):
        return await self.request(
            method='PATCH',
            url=self.BB_BASE_URL + resource,
            json=json,
            **kwargs
        )

    def set_cookies(self, cookies):
        for cookie in cookies:
            self.client.cookies.set(cookie['name'], cookie['value'], '.bestbuy.com', '/')


class BBApiException(Exception):
    pass


class BBBot:
    def __init__(self, api_client: BBApiClient, browser_client: BBBrowserClient):

        self.api_client = api_client
        self.browser_client = browser_client
        self.lock = asyncio.Lock()

        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s', '%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)

        log_path = Path('./logs')
        log_path.mkdir(exist_ok=True)

        file_handler = logging.FileHandler('./logs/bbbot.log')
        file_handler.setFormatter(formatter)

        self.logger = logging.getLogger('BBBot')
        self.logger.addHandler(handler)
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)

        self.order = None

    async def close(self):
        await self.api_client.close()

    def login(self):
        self.browser_client.login()
        self.logger.info('Logged in!')

    async def check_status(self, sku: str):
        response = await self.api_client.get(f'/api/3.0/priceBlocks?skus={sku}')
        return response.json()[0]['sku']['buttonState']['buttonState'] == 'ADD_TO_CART'

    async def add_to_cart(self, sku: str):
        response = await self.api_client.post('/cart/api/v1/addToCart', {'items': [{'skuId': sku}]})
        return response.json()['cartCount'] > 0

    async def check_in_cart(self):
        response = await self.api_client.get('/basket/v1/basketCount', headers={'x-client-id': 'browse'})
        return response.json()['count'] > 0

    async def get_order(self):
        response = await self.api_client.post('/cart/checkout', json=None)
        return response.json()['updateData']['order']

    async def get_fast_track(self):
        response = await self.api_client.get('/checkout/r/fast-track')
        return response

    async def set_shipping_info(self):
        order_id = self.order['id']
        payload = [{
            'id': self.order['lineItems'][0]['id'],
            'selectedFulfillment': {
                'shipping': {}
            }
        }]

        set_shipping_response = await self.api_client.patch(f'/checkout/orders/{order_id}/items', json=payload)

        payload = {
            'items': [{
                'giftMessageSelected': False,
                'id': self.order['lineItems'][0]['id'],
                'type': 'DEFAULT',
                'selectedFulfillment': {
                    'shipping':  {
                        "address": {
                            "country": "US",
                            "saveToProfile": False,
                            "street2": "",
                            "useAddressAsBilling": True,
                            "middleInitial": "",
                            "lastName": "Johnson",
                            "street": "9671 N Ox Brg",
                            "city": "Eagle Mountain",
                            "override": False,
                            "zipcode": "84005",
                            "state": "UT",
                            "firstName": "Zachary",
                            "isWishListAddress": False,
                            "dayPhoneNumber": "9728323923",
                            "type": "RESIDENTIAL"
                        }
                    }
                }
            }]
        }
        response = await self.api_client.patch(f'/checkout/orders/{order_id}', json=payload)
        return response

    async def refresh_payment_options(self):
        order_id = self.order['id']
        response = await self.api_client.post(f'/checkout/orders/{order_id}/paymentMethods/refreshPayment', json={})
        self.order = response.json()

    async def validate_order(self):
        order_id = self.order['id']
        response = await self.api_client.post(f'/checkout/orders/{order_id}/validate', None)
        return response

    async def get_default_card(self):
        response = await self.api_client.get('/profile/rest/c/paymentinfo/creditcard/all')
        cards = response.json()
        for card in cards:
            if card['primary']:
                return card

    async def set_payment_method(self):
        target_card = await self.get_default_card()
        order_card = self.order['paymentMethods']['creditCard']
        card_info = {
            'binNumber': order_card['binNumber'],
            'creditCardProfileId': target_card['id'],
            "cvv": CC_CCV,
            'expMonth': target_card['expirationDate']['month'],
            'expYear': target_card['expirationDate']['year'],
            'hasCID': False,
            'invalidCard': False,
            'isCustomerCard': False,
            'isNewCard': False,
            'isPWPRegistered': False,
            'isVisaCheckout': False,
            'orderId': self.order['customerOrderId'],
            'paymentReferenceId': order_card['paymentReferenceId'],
            'saveToProfile': False,
            'type': target_card['type'],
            'virtualCard': False,
        }

        target_billing = self.order['paymentMethods']['billingAddress']

        billing_info = {
            'addressLine1': target_billing['street'],
            'addressLine2': "",
            'city': target_billing['city'],
            'country': target_billing['country'].upper(),
            'dayPhone': target_billing['dayPhoneNumber'],
            'firstName': target_billing['firstName'],
            'isWishListAddress': False,
            'lastName': target_billing['lastName'],
            'middleInitial': "",
            'postalCode': target_billing['zipcode'],
            'standardized': True,
            'state': target_billing['state'],
            'useAddressAsBilling': True,
            'userOverridden': False,
        }

        payload = {
            'creditCard': card_info,
            'billingAddress': billing_info,
        }

        payment_id = self.order['payment']['id']
        response = await self.api_client.put(
            f'/payment/api/v1/payment/{payment_id}/creditCard',
            payload,
            headers={'x-context-id': self.order['customerOrderId'], 'x-client': 'CHECKOUT'}
        )
        return response

    async def authorize_payment(self):
        payment_id = self.order['payment']['id']
        stats_payload = {
            'orderId': self.order['id'],
            'browserInfo': {
                'javaEnabled': False,
                'language': 'en-US',
                'userAgent': BBApiClient.USER_AGENT,
                'height': '1127',
                'width': '1127',
                'timeZone': '420',
                'colorDepth': '24'
            }

        }
        stats_response = await self.api_client.post(
            f'/payment/api/v1/payment/{payment_id}/threeDSecure/preLookup',
            stats_payload,
            headers={'x-context-id': self.order['customerOrderId'], 'x-client': 'CHECKOUT'}
        )
        stats_id = stats_response.json()['threeDSReferenceId']

        payment_payload = {
            'orderId': self.order['id'],
            'threeDSecureStatus': {
                'threeDSReferenceId': stats_id
            }
        }
        response = await self.api_client.post('/checkout/api/1.0/paysecure/submitCardAuthentication', json=payment_payload)

        return response

    async def complete_checkout(self):
        order_id = self.order['id']
        response = await self.api_client.post(f'/checkout/orders/{order_id}', {
            'browserInfo': {
                'javaEnabled': False,
                'language': 'en-US',
                'userAgent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36',
                'height': '1127',
                'width': '1127',
                'timeZone': '420',
                'colorDepth': '24'
            }
        })

        return response

    async def run(self, sku: str):
        try:
            available = await self.check_status(sku)
            while not available:
                self.logger.info(f'Item {sku} not in stock...')
                await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
                available = await self.check_status(sku)
            self.logger.info(f'Item {sku} available!')
            async with self.lock:
                in_cart = await self.add_to_cart(sku)
                while not in_cart:
                    in_cart = await self.add_to_cart(sku)
                self.logger.info(f'Item {sku} in cart!')
                await self.get_fast_track()
                self.order = await self.get_order()
                await self.set_shipping_info()
                await self.refresh_payment_options()
                await self.validate_order()
                await self.set_payment_method()
                await self.refresh_payment_options()
                await self.authorize_payment()
                await self.complete_checkout()
                self.logger.info('Payment completed!')
                order_id = self.order['id']
                self.logger.info(f'Order {order_id} successfully completed!')
                await self.close()
        except KeyboardInterrupt as e:
            self.logger.info('Caught keyboard interrupt, closing down')
        except BBApiException as e:
            self.logger.warning(str(e.__class__.__name__) + ' ' + str(e))
            await self.run(sku)
        except Exception as e:
            self.logger.critical(str(e.__class__.__name__) + ' ' + str(e))
            await self.run(sku)

    async def attempt_to_buy(self, skus: list):
        if len(skus) == 0:
            raise ValueError('Skus not defined!')
        self.login()
        self.api_client.set_cookies(self.browser_client.cookies)
        tasks = []
        for sku in skus:
            task = asyncio.create_task(self.run(sku))
            tasks.append(task)

        for task in tasks:
            await task


SKUS = os.getenv('SKUS', [])


async def main():
    async_client = httpx.AsyncClient(http2=True)
    api_client = BBApiClient(async_client)
    browser_client = BBBrowserClient()
    bot = BBBot(api_client, browser_client)
    await bot.attempt_to_buy(SKUS.split(','))

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        print('Caught keyboard interrupt, closing down')
