import os, re, json, requests
from copy import deepcopy
from base64 import b64encode as b64
from bs4 import BeautifulSoup
from pathlib import Path
from subprocess import Popen, PIPE, STDOUT

import numpy as np

from astropy.io import ascii
from astropy.coordinates import SkyCoord

from flask import Flask, Response, request, render_template

from flows import load_config
from flows.api import get_targets, get_target
from flows.api import get_datafiles, get_datafile
from flows.api import get_all_sites, get_site

from functools import lru_cache
get_datafile = lru_cache(maxsize=1000)(get_datafile.__wrapped__)

USERNAME, PASSWORD = None, None

app = Flask(__name__, template_folder='web', static_folder='web/static')

@app.route('/api/targets.php')
def api_targets():
    if 'target' in request.args:
        target = request.args['target']
        if target in targets:
            target = targets[target]
        else:
            if (target := get_target_by_id(target)) is None:
                return '""'
        return json.dumps(target)
    return json.dumps(list(targets.values()))

@app.route('/api/datafiles.php')
def api_datafiles():
    if 'fileid' in request.args:
        fileid = int(request.args['fileid'])
        for name in targets:
            for datafile in datafiles[name]:
                if datafile['fileid'] == fileid:
                    return datafile
    elif 'targetid' in request.args:
        targetid = int(request.args['targetid'])
        if (target := get_target_by_id(targetid)) is None:
            return '""'
        return str([datafile['fileid'] for datafile in datafiles[target['target_name']]])
    return '""'

@app.route('/api/reference_stars.php')
def api_catalogs():
    targetid = target_name = request.args['target']
    if (target := get_target_by_id(targetid)) is None and \
            (target := get_target_by_name(target_name)) is None:
        return '""'
    catalog = catalogs[target["target_name"]]
    catalog['target'] = targets[target["target_name"]]
    catalog['avoid'] = None
    return json.dumps(catalog)

@app.route('/api/sites.php')
def api_sites():
    if 'siteid' in request.args:
        siteid = int(request.args['siteid'])
        site = [s for s in sites if siteid == s['siteid']]
        site = site[0] if site else ''
        return json.dumps(site)
    return json.dumps(sites)

@app.route('/')
def index():
    targets = sorted(deepcopy(get_targets()), key=lambda t: t['target_name'])[::-1]
    local_targets = os.listdir(load_config().get('photometry', 'archive_local', fallback='/'))
    for target in targets:
        c = SkyCoord(target['ra'], target['decl'], unit='deg')
        target['ra'], target['decl'] = c.to_string('hmsdms').split()
        target['inserted'] = target['inserted'].strftime('%Y-%m-%d %H:%M:%S')
        target['local'] = target['target_name'] in local_targets
    return render_template('index.html', targets=targets)

@app.route('/<target>')
def target(target):
    if not (target := get_target_by_name(target)):
        return ''
    datafiles = [deepcopy(get_datafile(datafile)) for datafile in get_datafiles(target['targetid'], 'all')]
    datafiles = sorted(datafiles, key=lambda f: f['obstime'])
    archive = '%s/%s' % (load_config().get('photometry', 'archive_local', fallback=''), target['target_name'])
    output = '%s/%s' % (load_config().get('photometry', 'output', fallback=''), target['target_name'])
    fileids = {int(fileid): fileid for fileid in os.listdir(output)} if os.path.isdir(output) else {}
    for datafile in datafiles:
        fileid = fileids.get(datafile['fileid'], '')
        datafile['filename'] = filename = datafile['path'].split('/')[-1]
        datafile['sitename'] = get_site(datafile['site'])['sitename'] if not datafile['site'] is None else 'None'
        datafile['exptime'] = '%.2f' % datafile['exptime'] if not datafile['exptime'] is None else 'None'
        datafile['inserted'] = datafile['inserted'].strftime('%Y-%m-%d %H:%M:%S')
        datafile['is_local'] = os.path.isfile(f'{archive}/{filename}')
        datafile['has_phot'] = os.path.isfile(f'{output}/{fileid}/photometry.ecsv')
    return render_template('target.html', target=target, datafiles=datafiles, login={None: "true"}.get(USERNAME, "false"))

@app.route('/<target>/photometry.js')
def photometry(target):
    if not (target := get_target_by_name(target)):
        return ''
    output = load_config().get('photometry', 'output', fallback='')
    fileids = get_datafiles(target['targetid'], "all")
    photometry = dict()
    for fileid in os.listdir(f'{output}/%s' % target['target_name']) if os.path.isdir(f'{output}/%s' % target['target_name']) else []:
        if not int(fileid) in fileids:
            continue
        try:
            table = ascii.read(f'{output}/%s/{fileid}/photometry.ecsv' % target['target_name'])
        except FileNotFoundError:
            continue
        filt, mjd = table.meta['photfilter'], table.meta['obstime-bmjd']
        for i in np.where(table['starid'] <= 0)[0]:
            mag, err = table[i]['mag'], table[i]['mag_error']
            _filt = 's_' + filt if table[i]['starid'] else filt
            if not _filt in photometry:
                photometry[_filt] = []
            photometry[_filt].append((mjd, mag, err, 'fileid: %d' % int(fileid)))
    photometry = {filt: list(map(list, zip(*photometry[filt]))) for filt in sorted(photometry)}
    return render_template('photometry.js', photometry=photometry)

@app.route('/observatories.js')
def observatories():
    observatories = [[s["sitename"], s["longitude"], s["latitude"], s["elevation"]] for s in get_all_sites()]
    return render_template('observatories.js', observatories=observatories)

def download_datafile(fileid):

    datafile = get_datafile(fileid)
    archive = load_config().get("photometry", "archive_local", fallback='/')

    s = requests.Session()

    soup = BeautifulSoup(s.get("https://flows.phys.au.dk").content, "html.parser")
    token = soup.find("form", id="loginform").find("input", dict(name="token")).get("value")
    params = dict(token=token, username=USERNAME, password=PASSWORD)
    page = s.post("https://flows.phys.au.dk/login/login.php", params)

    fits = s.get("https://flows.phys.au.dk/catalog/download_file.php", params=dict(fileid=fileid))
    Path(os.path.dirname(f"{archive}/{datafile['path']}")).mkdir(parents=True, exist_ok=True)
    with open(f"{archive}/{datafile['path']}", "wb") as fd:
        fd.write(fits.content)

    if datafile["diffimg"]:

        fits = s.get("https://flows.phys.au.dk/catalog/download_file.php", params=dict(fileid=datafile["diffimg"]["fileid"]))
        Path(os.path.dirname(f"{archive}/{datafile['diffimg']['path']}")).mkdir(parents=True, exist_ok=True)
        with open(f"{archive}/{datafile['diffimg']['path']}", "wb") as fd:
            fd.write(fits.content)

    s.close()

@app.route('/<target>/<int:fileid>', methods=["GET", "POST"])
def datafile(target, fileid):
    if "username" in request.form:
        global USERNAME, PASSWORD
        USERNAME, PASSWORD = request.form["username"], request.form["password"]
    if not (target := get_target_by_name(target)):
        return ''
    archive = "%s/%s" % (load_config().get("photometry", "archive_local", fallback='/'), get_datafile(fileid)["path"])
    if not os.path.exists(archive):
        download_datafile(fileid)
    output = '%s/%s' % (load_config().get('photometry', 'output', fallback=''), target['target_name'])
    Path(output).mkdir(parents=True, exist_ok=True)
    fileids = {int(fileid): fileid for fileid in os.listdir(output)}
    try:
        photometry = ascii.read(f'{output}/{fileids[fileid]}/photometry.ecsv')
    except (FileNotFoundError, KeyError):
        photometry = [{'starid': 0, 'ra': target['ra'], 'decl': target['decl'], 'distance': 0}]
    try:
        with open(f'{output}/{fileids[fileid]}/photometry.log', 'r') as fd:
            log = fd.read()
    except (FileNotFoundError, KeyError):
        log = ''
    try:
        images = []
        for f in sorted(os.listdir(f'{output}/{fileids[fileid]}')):
            if f.split('.')[-1] != 'png':
                continue
            with open(f'{output}/{fileids[fileid]}/{f}', 'rb') as fd:
                images.append(b64(fd.read()).decode('utf-8'))
    except KeyError:
        pass
    return render_template('datafile.html', target=target, fileid=fileid, photometry=photometry, log=log, images=images)

@app.route('/<target>/<int:fileid>.fits')
def fits(target, fileid):
    archive = load_config().get('photometry', 'archive_local', fallback='/')
    try:
        datafile = get_datafile(fileid)
    except:
        return ''
    if 'subtracted' in request.args:
        try:
            path = f'{archive}/' + datafile['diffimg']['path']
        except:
            return ''
    else:
        path = f'{archive}/' + datafile['path']
    with open(path, 'rb') as fd:
        return fd.read()

@app.route('/<target>/<int:fileid>/run_photometry', methods=['GET'])
def run_photometry(target, fileid):
    def stream():
        cmd = "flows-photometry", "--fileid", str(fileid), "--no-imagematch", "--no-auto-download"
        with Popen(cmd, stdout=PIPE, stderr=STDOUT) as p:
            while p.poll() is None:
                stdout = p.stdout.readline().decode()
                yield f"event: message\ndata: {stdout}\n\n"
    return Response(stream(), mimetype='text/event-stream')

def get_target_by_id(targetid):
    for target in get_targets():
        if str(target['targetid']) == str(targetid):
            return target

def get_target_by_name(target_name):
    for target in get_targets():
        if target['target_name'] == target_name:
            return target

def main():
    return app.run()#debug=True)

if __name__ == '__main__':
    main()
