#!/usr/bin/env python
# -*- coding: utf-8 -*-
    
import logging
from raspiot.utils import CommandError, MissingParameter, InvalidParameter
from raspiot.libs.internals.task import Task
from raspiot.raspiot import RaspIotModule
import urllib
import urllib3
#import ssl
import json
import time

__all__ = [u'Openweathermap']

class Openweathermap(RaspIotModule):
    """
    OpenWeatherMap application.
    Returns current weather conditions and forecast.

    Note:
        https://openweathermap.org/api
    """
    MODULE_AUTHOR = u'Cleep'
    MODULE_VERSION = u'1.0.0'
    MODULE_PRICE = 0
    MODULE_DEPS = []
    MODULE_DESCRIPTION = u'Gets weather conditions using OpenWeatherMap service'
    MODULE_TAGS = [u'weather', u'forecast']
    MODULE_COUNTRY = None
    MODULE_URLINFO = None
    MODULE_URLHELP = None
    MODULE_URLSITE = None
    MODULE_URLBUGS = None

    MODULE_CONFIG_FILE = u'openweathermap.conf'
    DEFAULT_CONFIG = {
        u'apikey': None
    }

    OWM_WEATHER_URL = u'http://api.openweathermap.org/data/2.5/weather'
    OWM_FORECAST_URL = u'http://api.openweathermap.org/data/2.5/forecast'
    OWM_TASK_DELAY = 900
    OWM_WEATHER_CODES = {
        200: u'Thunderstorm with light rain',
        201: u'Thunderstorm with rain',
        202: u'Thunderstorm with heavy rain',
        210: u'Light thunderstorm',
        211: u'Thunderstorm',
        212: u'Heavy thunderstorm',
        221: u'Ragged thunderstorm',
        230: u'Thunderstorm with light drizzle',
        231: u'Thunderstorm with drizzle',
        232: u'Thunderstorm with heavy drizzle',
        300: u'Light intensity drizzle',
        301: u'Drizzle',
        302: u'Heavy intensity drizzle',
        310: u'Light intensity drizzle rain',
        311: u'Drizzle rain',
        312: u'Heavy intensity drizzle rain',
        313: u'Shower rain and drizzle',
        314: u'Heavy shower rain and drizzle',
        321: u'Shower drizzle',
        500: u'Light rain',
        501: u'Moderate rain',
        502: u'Heavy intensity rain',
        503: u'Very heavy rain',
        504: u'Extreme rain',
        511: u'Freezing rain',
        520: u'Light intensity shower rain',
        521: u'Shower rain',
        522: u'Heavy intensity shower rain',
        531: u'Ragged shower rain',
        600: u'Light snow',
        601: u'Snow',
        602: u'Heavy snow',
        611: u'Sleet',
        612: u'Shower sleet',
        615: u'Light rain and snow',
        616: u'Rain and snow',
        620: u'Light shower snow',
        621: u'Shower snow',
        622: u'Heavy shower snow',
        701: u'Mist',
        711: u'Smoke',
        721: u'Haze',
        731: u'Sand, dust whirls',
        741: u'Fog',
        751: u'Sand',
        761: u'Dust',
        762: u'Volcanic ash',
        771: u'Squalls',
        781: u'Tornado',
        800: u'Clear sky',
        801: u'Few clouds',
        802: u'Scattered clouds',
        803: u'Broken clouds',
        804: u'Overcast clouds',
        900: u'Tornado',
        901: u'Tropical storm',
        902: u'Hurricane',
        903: u'Cold',
        904: u'Hot',
        905: u'Windy',
        906: u'Hail',
        951: u'Calm',
        952: u'Light breeze',
        953: u'Gentle breeze',
        954: u'Moderate breeze',
        955: u'Fresh breeze',
        956: u'Strong breeze',
        957: u'High wind, near gale',
        958: u'Gale',
        959: u'Severe gale',
        960: u'Storm',
        961: u'Violent storm',
        962: u'Hurricane'
    }
    OWM_WIND_DIRECTIONS = [u'N',u'NNE',u'NE',u'ENE',u'E',u'ESE',u'SE',u'SSE',u'S',u'SSW',u'SW',u'WSW',u'W',u'WNW',u'NW',u'NNW',u'N']

    def __init__(self, bootstrap, debug_enabled):
        """
        Constructor

        Args:
            bootstrap (dict): bootstrap objects
            debug_enabled (bool): flag to set debug level to logger
        """
        #init
        RaspIotModule.__init__(self, bootstrap, debug_enabled)

        #members
        self.weather_task = None
        self.__owm_uuid = None
        self.__forecast = []
        self.http = urllib3.PoolManager()

        #events
        self.openweathermap_weather_update = self._get_event('openweathermap.weather.update')

    def _configure(self):
        """
        Configure module
        """
        #add openweathermap device
        if self._get_device_count()==0:
            owm = {
                u'type': u'openweathermap',
                u'name': u'OpenWeatherMap',
                u'lastupdate': None,
                u'celsius': None,
                u'fahrenheit': None,
                u'humidity': None,
                u'pressure': None,
                u'wind_speed': None,
                u'wind_direction': None
            }
            self._add_device(owm)

        #get device uuid
        devices = self.get_module_devices()
        if len(devices)==1:
            self.__owm_uuid = devices.keys()[0]
        else:
            #supposed to have only one device!
            raise Exception(u'Openweathermap should handle only one device')

        #update weather conditions
        last_update = devices[self.__owm_uuid][u'lastupdate']
        if last_update is None or last_update+self.OWM_TASK_DELAY<time.time():
            self.logger.debug(u'Update weather at startup')
            self._weather_task()

        #start weather task
        self.weather_task = Task(self.OWM_TASK_DELAY, self._weather_task, self.logger)
        self.weather_task.start()

    def _stop(self):
        """
        Stop module
        """
        if self.weather_task is not None:
            self.weather_task.stop()

    def _owm_request(self, url, params):
        """
        Request OWM api

        Args:
            url (string): request url
            params (dict): dict of parameters

        Returns:
            tuple: request response::

                (
                    status (int): request status code,
                    data (dict): request response data
                )

        """
        status = None
        resp_data = None
        try:
            self.logger.debug(u'Request params: %s' % params)
            resp = self.http.request('GET', url, fields=params)
            resp_data = json.loads(resp.data.decode('utf-8'))
            status = resp.status
            if status!=200:
                self.logger.error(u'OWM api response [%s]: %s' % (status, resp_data))

        except:
            self.logger.exception('Error while requesting requesting OWM API:')

        return (status, resp_data)
    
    def _get_weather(self, apikey):
        """
        Get weather condition

        Returns:
            dict: weather conditions
                http://openweathermap.org/current#parameter for output format

        Raises:
            InvalidParameter, CommandError
        """
        #check parameter
        if apikey is None or len(apikey)==0:
            raise MissingParameter(u'Parameter "apikey" is missing')

        #get position infos from system module
        resp = self.send_command(u'get_position', u'parameters')
        self.logger.debug(u'Get position from parameters module resp: %s' % resp)
        if not resp:
            raise CommandError('No response from parameters module')
        elif resp[u'error']:
            raise CommandError(resp[u'message'])
        position = resp[u'data']

        #request api
        (status, resp) = self._owm_request(self.OWM_WEATHER_URL, {u'appid': apikey, u'lat': position[u'latitude'], u'lon': position[u'longitude'], u'units': u'metric', u'mode': u'json'})
        self.logger.debug(u'OWM response: %s' % (resp))

        #handle errors
        if status==401:
            raise Exception(u'Invalid OWM api key')
        elif status!=200:
            raise Exception(u'Error requesting openweathermap api [%s]' % status)
        if u'cod' not in resp:
            raise Exception(u'Invalid OWM api response format. Is API changed?')
        elif resp[u'cod']!=200: #cod is int for weather request
            raise Exception(resp[u'message'] if u'message' in resp else 'Unknown error')

        return resp

    def _get_forecast(self, apikey):
        """
        Get forecast (5 days with 3 hours step)

        Returns:
            dict: forecast
                http://openweathermap.org/forecast5 for output format

        Raises:
            InvalidParameter, CommandError
        """
        #check parameter
        if apikey is None or len(apikey)==0:
            raise MissingParameter(u'Parameter "apikey" is missing')

        #get position infos from system module
        resp = self.send_command(u'get_position', u'parameters')
        self.logger.debug(u'Get position from parameters module resp: %s' % resp)
        if not resp:
            raise CommandError('No response from parameters module')
        elif resp[u'error']:
            raise CommandError(resp[u'message'])
        position = resp[u'data']

        #request api
        (status, resp) = self._owm_request(self.OWM_FORECAST_URL, {u'appid': apikey, u'lat': position[u'latitude'], u'lon': position[u'longitude'], u'units': u'metric', u'mode': u'json'})
        self.logger.info(u'OWM response: %s' % (resp))

        #handle errors
        if status==401:
            raise Exception(u'Invalid OWM api key')
        elif status!=200:
            raise Exception(u'Error requesting openweathermap api [%s]' % status)
        if u'cod' not in resp:
            raise Exception(u'Invalid OWM api response format. Is API changed?')
        elif resp[u'cod']!='200': #cod is string for forecast request
            raise Exception(resp[u'message'] if u'message' in resp else 'Unknown error')
        if u'list' not in resp:
            raise Exception(u'No forecast data retrieved')

        return resp[u'list']

    def _weather_task(self):
        """
        Weather task in charge to refresh weather condition every hours
        Send event with data::

            {
                lastupdate (int): timestamp,
                icon (string): openweathermap icon,
                condition (string): openweathermap condition string (english),
                code (int): openweather condition code,
                celsius (float): current temperature in celsius,
                fahrenheit (float): current temperature in fahrenheit,
                pressure (float): current pressure,
                humidity (float): current humidity,
                wind_speed (float): current wind speed,
                wind_direction (string): current wind direction,
                wind_degrees (float): current wind degrees
            }

        """
        try:
            self.logger.debug(u'Update weather conditions')
            #get api key
            config = self._get_config()
            if config[u'apikey'] is not None and len(config[u'apikey'])>0:
                #apikey configured, get weather
                weather = self._get_weather(config[u'apikey'])
                self.__forecast = self._get_forecast(config[u'apikey'])

                #save current weather conditions
                device = self._get_devices()[self.__owm_uuid]
                device[u'lastupdate'] = int(time.time())
                if weather.has_key(u'weather') and len(weather[u'weather'])>0:
                    if weather[u'weather'][0].has_key(u'icon'):
                        device[u'icon'] = u'http://openweathermap.org/img/w/%s.png' % weather[u'weather'][0][u'icon']
                    else:
                        device[u'icon'] = null
                    if weather[u'weather'][0].has_key(u'id'):
                        device[u'condition'] = self.OWM_WEATHER_CODES[weather[u'weather'][0][u'id']]
                        device[u'code'] = int(weather[u'weather'][0][u'id'])
                    else:
                        device[u'condition'] = None
                        device[u'code'] = None
                if weather.has_key(u'main'):
                    if weather[u'main'].has_key(u'temp'):
                        device[u'celsius'] = weather[u'main'][u'temp']
                        device[u'fahrenheit'] = weather[u'main'][u'temp'] * 9.0 / 5.0  + 32.0
                    else:
                        device[u'celsius'] = None
                        device[u'fahrenheit'] = None
                    if weather[u'main'].has_key(u'pressure'):
                        device[u'pressure'] = weather[u'main'][u'pressure']
                    else:
                        device[u'pressure'] = None
                    if weather[u'main'].has_key(u'humidity'):
                        device[u'humidity'] = weather[u'main'][u'humidity']
                    else:
                        device[u'humidity'] = None
                if weather.has_key('wind'):
                    if weather[u'wind'].has_key(u'speed'):
                        device[u'wind_speed'] = weather[u'wind'][u'speed']
                    else:
                        device[u'wind_speed'] = None
                    if weather[u'wind'].has_key('deg'):
                        device[u'wind_degrees'] = weather[u'wind'][u'deg']
                        index = int(round( (weather[u'wind'][u'deg'] % 360) / 22.5) + 1)
                        if index>=17:
                            index = 0
                        device[u'wind_direction'] = self.OWM_WIND_DIRECTIONS[index]
                    else:
                        device[u'wind_degrees'] = None
                        device[u'wind_direction'] = None
                self._update_device(self.__owm_uuid, device)

                #and emit event
                self.openweathermap_weather_update.send(params=device, device_id=self.__owm_uuid)

        except Exception as e:
            self.logger.exception(u'Exception during weather task:')

    def set_apikey(self, apikey):
        """ 
        Set openweathermap apikey

        Params:
            apikey (string): apikey

        Returns:
            bool: True if config saved successfully
        """
        if apikey is None or len(apikey)==0:
            raise MissingParameter(u'Parameter "apikey" is missing')

        #test apikey (should raise exception if error)
        self._get_weather(apikey)

        #save config
        return self._update_config({
            u'apikey': apikey
        })

    def get_weather(self):
        """
        Return current weather conditions
        Useful to use it in action script

        Returns:
            dict: device information
        """
        return self._get_devices()[self.__owm_uuid]

    def get_forecast(self):
        """
        Return last forecast information.
        May be empty if raspiot just restarted.

        Returns:
            list: list of forecast data (every 3 hours)
        """
        return self.__forecast
