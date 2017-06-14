#!/usr/bin/env python
from __future__ import print_function
from ipywidgets import *
from IPython.display import display
from getpass import getpass
import glob
import os
import stat
import paramiko
from string import Template
from os.path import expanduser
from pkg_resources import resource_string
from IPython.core.magic import (register_line_magic, register_cell_magic,register_line_cell_magic)
import hashlib
from itertools import izip,cycle
from IPython.display import IFrame

USERNAME = os.environ['USER']
CONF_DIR='.rg_conf'
CONF_MOD=int('700', 8) # exclusive access
CONF_FILE='%s/%s'%(CONF_DIR, USERNAME)
#ROGER_PRJ='/projects/class/jhub/users'
#JUPYTER_HOME='/mnt/jhub/users'
ROGER_PRJ='/projects/jupyter'
JUPYTER_HOME='/home'

def encrypt(plaintext):
    ciphertext = ''.join(chr(ord(x) ^ ord(y)) for (x,y) in izip(plaintext, cycle(hashlib.sha256(USERNAME).hexdigest())))
    return ciphertext.encode('base64')

def decrypt(ciphertext):
    ciphertext = ciphertext.decode('base64')
    return ''.join(chr(ord(x) ^ ord(y)) for (x,y) in izip(ciphertext, cycle(hashlib.sha256(USERNAME).hexdigest())))

def Labeled(label, widget):
    width='130px'
    return (Box([HTML(value='<p align="right" style="width:%s">%s&nbsp&nbsp</p>'%(width,label)),widget],
                layout=Layout(display='flex',align_items='center',flex_flow='row')))

def listExeutables(folder='.'):
    executable = stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
    return [filename for filename in os.listdir(folder)
        if os.path.isfile(filename)]# and (os.stat(filename).st_mode & executable)]

def tilemap(tif, name, overwrite=False, overlay=None,tilelvl=[9,13]):
    id=hashlib.sha1(name).hexdigest()[:10]
    if overwrite:
        os.system('rm -rf %s'%id)
    os.system('gdal2tiles.py -e -z %d-%d -a 0,0,0 -s epsg:4326 -r bilinear -t "%s" %s -z 8-14 %s'%(tilelvl[0], tilelvl[1], name,tif,id))
    with open('%s/leaflet.html'%id) as input:
        s=input.read()
    s=s.replace('http://cdn.leafletjs.com','https://cdn.leafletjs.com')
    s=s.replace('http://{s}.tile.osm.org','https://{s}.tile.openstreetmap.org')
    addLayer='map.addLayer(lyr);'
    if overlay:
        os.system("wget 'https://raw.githubusercontent.com/calvinmetcalf/leaflet-ajax/master/dist/leaflet.ajax.min.js' -O %s/leaflet.ajax.min.js"%id)
        s=s.replace('leaflet.js"></script>','leaflet.js"></script>\n<script src="leaflet.ajax.min.js"></script>')

        vectorNewLayers = []
        vectorOverlay = []
        vectorAdd = []
        for vecFile,vecName in overlay:
            vecId=hashlib.sha1(vecName).hexdigest()[:10]
            os.system('ogr2ogr -f "geojson" %s/%s.json %s'%(id,vecId,vecFile))
            vectorNewLayers.append('var vecLayer%s = new L.GeoJSON.AJAX("%s.json");'%(vecId,vecId))
            vectorOverlay.append('"%s":vecLayer%s'%(vecName, vecId))
            vectorAdd.append('map.addLayer(vecLayer%s);'%vecId)

        s=s.replace('// Map','\n'.join(vectorNewLayers)+'\n // Map')
        s=s.replace('{"Layer": lyr}','{'+','.join(vectorOverlay)+', "Layer": lyr}')
        addLayer+='\n'.join(vectorAdd)

    s=s.replace(').addTo(map);',').addTo(map); '+addLayer)
    with open('%s/leaflet.html'%id,'w') as output:
        output.write(s)
    return IFrame('%s/leaflet.html'%id, width='1000',height='600')

class Job():
    def __init__(self):
        #user=widgets.Text(value=USERNAME,placeholder='Your ROGER Account name', description='Username',disabled=False)
        #display(user)
        #pw=getpass(prompt='Password')

        #paramiko.util.log_to_file("ssh.log")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.homeDir = '%s/%s'%(JUPYTER_HOME,USERNAME)
        self.jobDir = self.homeDir + '/.jobs'
        if not os.path.exists(self.jobDir):
            os.makedirs(self.jobDir)
        self.userName = USERNAME
        self.rogerRoot = '%s/%s'%(ROGER_PRJ, self.userName)
        self.rogerJobDir = self.rogerRoot + '/.jobs'
        self.relPath = os.path.relpath(os.getcwd(), self.homeDir)
        self.rogerPath = self.rogerRoot + '/' + self.relPath
        self.editMode = True
        self.jobId = None
        with open(os.path.dirname(__file__)+'/qsub.template') as input:
            self.job_template=Template(input.read())
        self.login()
        
    def login(self):
        
        if not os.path.exists(CONF_DIR):
            os.makedirs(CONF_DIR)
    
        if stat.S_IMODE(os.stat(CONF_DIR).st_mode)!=CONF_MOD:
            os.chmod(CONF_DIR, stat.S_IREAD | stat.S_IWUSR | stat.S_IXUSR)
            
        if not os.path.exists(CONF_FILE):
            #user=widgets.Text(value=USERNAME,placeholder='Your Roger Username', description='Username',disabled=False)
            #display(user)
            login_success = False
            while not login_success:
                pw=getpass(prompt='Password')
                try:
                    self.client.connect('roger-login.ncsa.illinois.edu', username=USERNAME, password=pw)
                    self.sftp=self.client.open_sftp()
                except Exception as e:
                    print(e)
                else:
                    print('Successfully logged in as %s'%self.userName)        
                    login_success = True

            with open(CONF_FILE,'w') as output:
                output.write(encrypt(pw))
                    
        else:
            pw=decrypt(open(CONF_FILE).read())

            try:
                self.client.connect('roger-login.ncsa.illinois.edu', username=USERNAME, password=pw)
                #key = paramiko.RSAKey.from_private_key_file(self.homeDir+'/.ssh/roger.key')
                #self.client.connect('roger-login.ncsa.illinois.edu', username='dyin4', pkey = key)
                self.sftp=self.client.open_sftp()
            except Exception as e:
                print(e)
            else:
                print('Successfully logged in as %s'%self.userName)        
        
    def submit(self,jobName='test',entrance='test.sh',nNodes=4,ppn=1,isGPU=False,walltime=1,submit=False,hideUI=False):
        self.jobName=jobName
        self.entrance=entrance
        self.nNodes=nNodes
        self.ppn=ppn
        self.isGPU=isGPU
        self.walltime=walltime
        res=self.__submitUI(submit,hideUI)
        if submit and hideUI:
            return res

    def __runCommand(self, command):
        stdin,stdout,stderr = self.client.exec_command(command)
        return ''.join(stdout.readlines())+''.join(stderr.readlines())

    def __submitUI(self, direct_submit=False,hideUI=False):
        fileList=listExeutables()
        if len(fileList) == 0:
            with open('test.sh','w') as output:
                output.write('#!/bin/bash\n\necho test')

        jobName=Text(value=self.jobName)
        entrance=Dropdown(
            options=fileList,
            value=fileList[0],
            layout=Layout()
        )
        nNodes=IntSlider(
            value=self.nNodes,
            min=1,
            max=10,
            step=1,
            continuous_update=False,
            orientation='horizontal',
            readout=True,
            readout_format='i',
            slider_color='white'
        )
        ppn=IntSlider(
            value=self.ppn,
            min=1,
            max=20,
            step=1,
            continuous_update=False,
            orientation='horizontal',
            readout=True,
            readout_format='i',
            slider_color='white'
        )
        isGPU=RadioButtons(
            options=['No GPU','GPU'],
            value = 'GPU' if self.isGPU else 'No GPU'
        )
        ppn=IntSlider(
            value=self.ppn,
            min=1,
            max=20,
            step=1,
            continuous_update=False,
            orientation='horizontal',
            readout=True,
            readout_format='i',
            slider_color='white'
        )
        walltime=FloatSlider(
            value=float(self.walltime),
            min=1.0,
            max=48.0,
            step=1.0,
            continuous_update=False,
            orientation='horizontal',
            readout=True,
            readout_format='.1f',
            slider_color='white'
        )
        preview=Button(
            description='Preview Job script',
            button_style='', # 'success', 'info', 'warning', 'danger' or ''
            tooltip='Preview Job'
        )
        jobview=Textarea(
            layout=Layout(width='500px',height='225px',max_width='1000px', max_height='1000px')
        )
        confirm=Button(
            description='Submit Job',
            button_style='', # 'success', 'info', 'warning', 'danger' or ''
            tooltip='Submit job'
        )
        status=HTML(
            layout=Layout(width='850px',height='200px',max_width='1000px', min_height='200px', max_height='1000px')
        )
        refresh=Button(
            description='Refresh Status',
            disabled=True
        )
        cancel=Button(
            description='Cancel Job',
            disabled=True
        )
        newJob=Button(
            description='New Job',
            disabled=True
        )
        jobEdits = [jobName,entrance,nNodes,ppn,isGPU,walltime,confirm]
        postSubmission = [refresh, cancel, newJob]
        
        def switchMode():

            if not self.editMode:
                status.value = ''
                
            for w in jobEdits:
                w.disabled = self.editMode
            jobview.disabled = self.editMode
            
            self.editMode = not self.editMode
            for w in postSubmission:
                w.disabled = self.editMode
                    
        
        def click_preview(b):
            jobview.value=self.job_template.substitute(
                  jobname  = jobName.value, 
                  n_nodes  = nNodes.value, 
                  is_gpu   = isGPU.value.lower().replace(' ',''),
                  ppn      = ppn.value,
                  walltime = '%d:00:00'%int(walltime.value), 
                  username = self.userName, 
                  jobDir   = self.rogerJobDir,
                  rogerPath= self.rogerPath,
                  exe      = entrance.value
            )
        click_preview(1)
        preview.on_click(click_preview)    
        
        for w in jobEdits:
            w.observe(click_preview, names='value')
  
        def refreshStatus(b):
            #status.value='<pre>'+self.__runCommand('date; qstat  | awk \'NR < 3 || /%s/\''%(self.username))+'</pre>'
            if self.jobId is None:
                status.value='<pre><font size=2>%s</font></pre>'%('\n'*8)
                return
            
            result = self.__runCommand('date; qstat -a %s | sed 1,3d '%self.jobId)                
            if 'Unknown Job Id Error' in result:
                result = 'Job %s is finished'%self.jobId
                est_time= '\n'*7
                
            else:
                est_time = self.__runCommand('showstart %s | head -3'%self.jobId)
                if 'cannot locate job' in est_time:
                    est_time = 'Job %s is currently out of queue.\n\n'%self.jobId
                
            status.value='<pre><font size=2>%s\n%s</font></pre>'%(result, est_time)
            
        refreshStatus(1)
        refresh.on_click(refreshStatus)
        
        def submit(b):
            filename='%s.pbs'%jobName.value
            with open(self.jobDir + '/' + filename,'w') as output:
                output.write(jobview.value)
            self.jobId = self.__runCommand('qsub %s/%s 2>/dev/null'%(self.rogerJobDir, filename)).strip()
            switchMode()
            refreshStatus(1)
            #status.value='<pre>'+self.__runCommand('qsub %s >/dev/null 2>&1; date; qstat | awk \'NR < 3 || /%s/ \''%(filename,self.username))+'</pre>'
            #status.value='<pre><font size=2>'+self.__runCommand('date; qstat -u %s | sed 1,3d'%(self.userName))+'</font></pre>'
        
        confirm.on_click(submit)
        
        def click_cancel(b):
            if self.jobId:
                self.__runCommand('qdel %s'%self.jobId)
            switchMode()
        
        cancel.on_click(click_cancel)
        
        def click_newJob(b):
            switchMode()
        
        newJob.on_click(click_newJob)
        
        submitForm=VBox([
                Labeled('Job name', jobName),
                Labeled('Executable', entrance),
                Labeled('No. nodes', nNodes),
                Labeled('Cores per node', ppn),
                Labeled('GPU needed', isGPU),
                Labeled('Walltime (h)', walltime),
                #Labeled('', preview),
                Labeled('Job script', jobview),
                Labeled('', confirm)
            ])
        statusTab=VBox([
                Labeled('Job Status', status),
                Labeled('', HBox([refresh,cancel,newJob])),
        ])

        if direct_submit:
            submit(1)
            
        #display(Tab([submitForm, statusTab], _titles={0: 'Submit New Job', 1: 'Check Job Status'}))
        if direct_submit:
            if hideUI:
                return self.jobId
            else:
                display(VBox([
                    Labeled('Job script', jobview),
                    VBox([
                        Labeled('Job Status', status),
                        Labeled('', HBox([refresh,cancel])),
                    ])
                ]))
        else:
            display(VBox([submitForm, statusTab]))

            
    def listRunning(self, user=USERNAME, hideUI=False):
        header=HTML(
            layout=Layout(width='800px',max_width='1000px', 
                          min_width='50px', max_height='1000px')
        )
        status=SelectMultiple(
            layout=Layout(width='850px',height='125px',max_width='1000px', 
                          min_width='800px', min_height='125px', max_height='1000px')
        )
        refresh=Button(
            description='Refresh Status',
            disabled=False
        )
        cancel=Button(
            description='Cancel Job',
            disabled=False
        )        
        
        def refreshStatus(b):
            #status.value='<pre>'+self.__runCommand('date; qstat  | awk \'NR < 3 || /%s/\''%(self.username))+'</pre>'
            result = self.__runCommand("qstat | sed -n '1,2p;/%s/p'"%user)
            header.value='<pre>%s</pre>'%result
            self.runningIds = [_.split()[0] for _ in result.strip().split('\n')[2:]]
            #status.options = [_.split()[0] for _ in result.strip().split('\n')[2:]]
            
        refreshStatus(1)
        refresh.on_click(refreshStatus)
        
        def click_cancel(b):
            pass
            #self.__runCommand('qdel %s'%status.value[0].split()[0])
        
        cancel.on_click(click_cancel)
        
        if not hideUI:
            display(
                VBox([
                    header,
                    #HBox([status,header]),
                    #status,
                    HBox([refresh, cancel])
                ])
            )
        else:
            return self.runningIds
        
    def cancel(self, jobIds):
        if isinstance(jobIds, str):
            self.__runCommand('qdel %s'%jobIds)
        elif isinstance(JobIds, list):
            self.__runCommand('qdel %s'%' '.join(jobIds))
    
    #def showDetail(self, jobId): # Not handling large output
    #    print(self.__runCommand('qstat -f %s'%jobId))

#@register_line_magic
#def roger(line):
#    Roger()
#del roger
