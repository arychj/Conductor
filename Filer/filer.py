#!/usr/bin/env python

import datetime, glob, grp, time, os, pwd, re, shutil, smtplib, string, sys, urllib, urllib2
import xml.etree.ElementTree as ET
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from sys import stdout

_config = None

def LoadConfig(file):
	global _config
	tree = ET.parse(file)
	_config = tree.getroot()

def Write(value):
	stdout.write(value)
	stdout.flush()

def Send(to, subject, body):
	message = MIMEMultipart('alternative')
	message['Subject'] = subject
	message['From'] = _config.find('notifications/from').text
	message['To'] = to

	try:
		body = re.sub(_config.find('regex/safeemail').text, '', body)

		part1 = MIMEText(re.sub('</?[a-zA-Z0-9]+/?>', '', body), 'plain')
		part2 = MIMEText(body, 'html')

		message.attach(part1)
		message.attach(part2)

		server = smtplib.SMTP(_config.find('notifications/mailhost').text)
		server.starttls()
		server.login(_config.find('notifications/credentials/username').text, _config.find('notifications/credentials/password').text)
		server.sendmail(message['From'], message['To'], message.as_string())
		server.quit()
	except Exception as e:
		return str(e)

	return None

def Sanitize(s):
    return re.sub(_config.find('regex/safefilename').text, '', s)

def GetOverride(type, name):
	for series in _config.findall('overrides/' + type + '/override'):
		if re.search(series.get('pattern'), name):
			if type == 'season' and series.get('action') != None:
				if series.get('action') == 'add':
					return int(series.text)
				elif series.get('action') == 'sub':
					return -1 * int(series.text)
			else:
				return series.text

	#defaults
	if type == 'season':
		return 0
	elif type == 'name' and name[:3] == 'The':
		return name[4:] + ', The'
	else:
		return name

def CallTVDB(service, params):
	params = urllib.urlencode(params)
	
	url = _config.find('tvdb/serviceurl').text + '/' + service + '.php?apikey=' + _config.find('tvdb/apikey').text + '&' + params
	stream = urllib2.urlopen(url)
	sResponse = stream.read();
	
	response = ET.fromstring(sResponse)

	return response

def ParseFile(file):
	Write('\n\tParsing name... ')

	details = {
		'Found': False,
		'SearchName': None,
		'SeriesName': None,
		'SeasonNumber': None,
		'EpisodeName': None,
		'EpisodeNumber': None,
		'EpisodeDescription': None,
		'EpisodeId': None,
		'AirDate': None,
		'Extension': None,
		'EpisodeType': None,
		'Supersede': None,
		'AdditionalInfo': ''
	}

	safefilename = Sanitize(file)
	extension = re.search(_config.find('regex/extension').text, safefilename).groups()[0]
	episodetype = _config.find('regex/episode[@extension=\'' + extension + '\']')

	#if known file type
	if episodetype != None:
		details['EpisodeType'] = episodetype.get('type')
		if episodetype.get('supersede') != None:
			details['Supersede'] = episodetype.get('supersede')

		m = re.match(episodetype.text, safefilename)
		if m != None:
			Write('done.')
			
			details['SearchName'] = GetOverride('search', m.group('seriesname'))
			details['SeriesName'] = GetOverride('name', m.group('seriesname'))
			details['SeasonNumber'] = int(m.group('seasonnumber')) + GetOverride('season', details['SearchName'])
			details['EpisodeNumber'] = int(m.group('episodenumber'))
			details['EpisodeName'] = m.group('episodename')
			details['AirDate'] = m.group('airdate')
			details['Extension'] = m.group('extension')

			if _config.find('settings/alphapostthe').text == 'True':
				if details['SeriesName'][:3] == 'The':
					details['SeriesName'] = details['SeriesName'][4:] + ', The'

			try:
				Write('\n\tQuerying series archive... ')

				if details['SeasonNumber'] != None and details['EpisodeNumber'] != None:
					try:
						api = __import__('pytvdbapi', fromlist=['api']).api
						tvdb = api.TVDB(_config.find('tvdb/apikey').text)
						series = tvdb.search(details['SearchName'], 'en')[0]
						
						series.update()
						episode = series[details['SeasonNumber']][details['EpisodeNumber']]

						if episode != None:
							Write('found.')

							details['Found'] = True
							details['EpisodeId'] = 'S' + str(episode.SeasonNumber).zfill(2) + 'E' + str(episode.EpisodeNumber).zfill(2)
							details['EpisodeName'] = Sanitize(episode.EpisodeName)
							details['EpisodeDescription'] = episode.Overview
							details['AirDate'] = episode.FirstAired
					except:
						pass

				if details['Found'] == False:
					Write('not found.\n\tQuerying episode airdate... ')
					rSeries = CallTVDB('GetSeries', {'seriesname': details['SearchName']})
					seriesid = rSeries.findall('./Series/seriesid')[0].text
					rEpisode = CallTVDB('GetEpisodeByAirDate', {'seriesid': seriesid, 'airdate': details['AirDate'].replace('_', '-')})

					if len(rEpisode.findall('./Error')) == 0:
						Write('found.')

						details['Found'] = True
						details['EpisodeId'] = 'S' + str(rEpisode.findall('./Episode/SeasonNumber')[0].text).zfill(2) + 'E' + str(rEpisode.findall('./Episode/EpisodeNumber')[0].text).zfill(2)
						details['AirDate'] = rEpisode.findall('./Episode/FirstAired')[0].text
						details['EpisodeName'] = Sanitize(rEpisode.findall('./Episode/EpisodeName')[0].text)
						details['EpisodeDescription'] = rEpisode.findall('./Episode/Overview')[0].text
					else:
						Write('not found.')
			except:
				Write('error.')
		else:
			Write('unknown file name format.')
	else:
		Write('unknown file type.')

	return details

def Notify(details):
	Write('\n\tEmailing notice to \'' + _config.find('notifications/to').text + '\'... ')
	try:
		subject = string.Template(_config.find('notifications/subject').text).substitute(details)
		body = string.Template(_config.find('notifications/body').text).substitute(details)

		sendresult = Send(_config.find('notifications/to').text, subject, body)
		if sendresult == None:
			Write('done.')
		else:
			Write(sendresult)
	except Exception as e:
		Write(e.message)

def SetPermissions(path):
	permissions = _config.find('permissions')
	if permissions != None and permissions.get('set') == 'True':
		type = 'file' if os.path.isfile(path) else 'directory'
		mode = int(_config.find('permissions/' + type + '/mode').text, 8)
		uid = pwd.getpwnam(_config.find('permissions/' + type + '/user').text).pw_uid
		gid = grp.getgrnam(_config.find('permissions/' + type + '/group').text).gr_gid

		os.chmod(path, mode)
		os.chown(path, uid, gid)

def FileEpisode(details, seriesdirectory = None):
	if seriesdirectory == None:
		if _config.find('directories/destination').get('split') != None:
			buckets = int(_config.find('directories/destination').get('split'))
			bucket = None

			start = 'A'
			for i in xrange(26/buckets, (26 + 1), 26/buckets):
				if ord(details['SeriesName'][0].upper()) - ord('A') < i:
					bucket = start + '-' + chr(ord('A') + i - 1)
					break
				else:
					start = chr(ord('A') + i)
			
			seriesdirectory = _config.find('directories/destination').text + '/' + bucket + '/' + details['SeriesName'] + '/Season ' + str(details['SeasonNumber'])
		else:
			seriesdirectory = _config.find('directories/destination').text + '/' + details['SeriesName'] + '/Season ' + str(details['SeasonNumber'])

	destpath = seriesdirectory + '/' + details['Filename']

	Write('\n\t\tMoving to \'' + destpath + '\'... ')

	if os.path.isdir(seriesdirectory) != True:
		if _config.find('settings/debug').text != 'False':
			Write('\n\n>>> fake directory create ' + seriesdirectory + '<<<')
		else:
			os.makedirs(seriesdirectory)
			SetPermissions(seriesdirectory)
	
	existingEpisodes = glob.glob(_config.find('directories/destination').text + '/*/' + details['SeriesName'] + '/*/' + details['EpisodeId'] + '*')
	if len(existingEpisodes) == 0:
		if _config.find('settings/debug').text != 'False':
			Write('\n\n>>> fake file move <<<\n')
		else:
			shutil.move(details['SourcePath'], destpath)
			SetPermissions(destpath)
		Write('done.')
		return destpath
	elif details['Supersede'] == 'True':
		Write('episode exists, superseding... ')
		details['AdditionalInfo'] += existingEpisodes[0] + ' superseded'

		if _config.find('settings/debug').text != 'False':
			Write('\n\n>>> fake file move <<<\n')
		else:
			os.remove(existingEpisodes[0])
			shutil.move(details['SourcePath'], destpath)
			SetPermissions(destpath)
		Write('done.')
		return destpath
	else:
		Write('episode exists.')
		if _config.find('settings/debug').text != 'False':
			Write('\n\n>>> fake file move <<<\n')
		else:
			shutil.move(details['SourcePath'], _config.find('directories/problems').text + '/' + f)
		Write('\n\t\tPlaced in problems directory.')
		return None

def Discover():
	outputstarted = False
	root = _config.find('directories/source').text

	listing = os.listdir(root)
	for f in listing:
		sourcepath = root + '/' + f

		if os.path.isfile(sourcepath):
			if outputstarted == False:
				outputstarted = True
				Write('\n' + str(datetime.datetime.now()) + '\n')

			Write('\n' + f)

			#ensure file is not currently being copied
			Write('\n\tChecking xfer status... ')
			sizecheck0 = os.path.getsize(sourcepath)
			time.sleep(int(_config.find('delays/transfercheck').text))
			sizecheck1 = os.path.getsize(sourcepath)

			#if the file size has changed then transfer is in prtress, skip the file
			if sizecheck0 != sizecheck1:
				Write('xfer not complete.\n')
				continue
			else:
				Write('done.')

			details = ParseFile(f)
			details['SourcePath'] = sourcepath
			details['AddedOn'] = datetime.datetime.now().strftime('%Y-%m-%d')

			if details['Found'] == True:
				details['Filename'] = details['EpisodeId'] + ' - ' + details['EpisodeName'] + '.' + details['Extension']

				Write('\n\tFiling episode... ')

				details['DestinationPath'] = FileEpisode(details)
				if details['DestinationPath'] != None and _config.find('settings/notify').text == 'True':
					Notify(details)
			else:
				Write('\n\tMoving to problem dir... ')

				details['Filename'] = f
				if FileEpisode(details, _config.find('directories/problems').text):
					Write('done.')

	Write('\n')

### run the program ###
if len(sys.argv) != 2:
	print '\tUsage: ' + sys.argv[0] + ' config.xml'
else:
	LoadConfig(sys.argv[1])
	Discover()
