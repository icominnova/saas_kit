import os,time,sys
import random, string
# import json
import subprocess
import shutil
# import argparse
import logging
import functools
import xmlrpc.client
import socket
import logging
from collections import defaultdict
from contextlib import closing
from configparser import ConfigParser
from . import saas_client_db
from .  pg_query import PgQuery 
from .. static_saas_kit import SAAS_ODOO_VERSIONS


_logger = logging.getLogger(__name__)

try:
    import docker
except ImportError as e:
    _logger.info("Docker Library not installed!!")
     
try:
    import erppeek
except ImportError as e:
    _logger.info("erppeek library not installed!!")
   
class odoo_container:
    def  __init__(self,db="dummy",odoo_image="odoobywebkul:19.0",odoo_config = None,host_server = None, db_server = None, version = "19.0"):
        self.location = odoo_config
        self.remote_host = host_server['host']
        self.remote_port = host_server['port']
        self.remote_user = host_server['user']
        self.remote_password = host_server['password']
        self.default_version = version
        self.db_host = db_server['host']
        self.db_port = db_server['port']
        self.db_user = db_server['user']
        self.db_password = db_server['password']
        self.response = {}
        self.read_variables(self.location+"/models/lib/saas.conf")

    def read_variables(self,path):
        _logger.info("Reading Conf from %r"%path)
        parser = ConfigParser()
        parser.read(path)
        version = self.default_version.split(".")[0]
        _logger.info("Version %r"%version)

        self.template_master = parser.get("options","template_master")
        self.container_master = parser.get("options","container_master")
        self.container_user = parser.get("options","container_user")
        self.odoo_config = parser.get("options","odoo_saas_data")
        self.container_passwd = parser.get("options","container_passwd")
        self.template_odoo_port = parser.get("options","template_odoo_port_v"+version)
        self.template_odoo_lport = parser.get("options","template_odoo_lport_v"+version)
        self.common_addons = parser.get("options","common_addons_v"+version)
        self.odoo_template = parser.get("options","odoo_template_v"+version)
        self.data_dir = parser.get("options","data_dir_path")
        self.odoo_image = parser.get("options","odoo_image_v"+version)
        self.response['odoo_image'] = self.odoo_image
        self.ports_in_use = { self.template_odoo_port,  self.template_odoo_lport }
        _logger.info("Reading Conf from %r:- Done"%path)

    def get_client(self):
        try:
            self.dclient = docker.from_env()
        except Exception as e:
            _logger.error("Docker Library not installed!!")
            raise e
        return True
    
    def check_error(self,func):
        functools.wraps(func)
        def wrapper(*args,**argc):
            try:
                return func(*args,**argc)
            except Exception as e:
                _logger.error("Error %s occurred at %s"%(str(e),func.__name__))
                exit(1)
        return wrapper

    def list_all_used_ports(self):
        containers = self.dclient.containers.list(all)
        for each in containers:
            port_info =  each.attrs['HostConfig']['PortBindings']
            if port_info and port_info.get('8069/tcp',None):
                self.ports_in_use.add(port_info['8069/tcp'][0]['HostPort'])
                if port_info.get('8071/tcp',None):
                    self.ports_in_use.add(port_info['8071/tcp'][0]['HostPort'])
#        return self.ports_in_use
    
    def find_me_an_available_port_within(self,a,b):
        self.list_all_used_ports()
        _logger.info("++Ports already In use+%r",str(self.ports_in_use))
        for port in range(b, a, -1):
             if str(port) in self.ports_in_use:
                 _logger.info("Port %r  already in use",port)
                 continue
             _logger.info("Port %r seems available",port)
             with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                 res = sock.connect_ex(('localhost', port))
                 if res != 0:
                     self.response['port'] =  port
                     self.ports_in_use.add(str(port))
                     return port
        _logger.info("All the ports are being used. Try removing unused or obsolete containers")
        return False
    
    def random_str(self,length):
        letters = string.ascii_uppercase
        return ''.join(random.choice(letters) for i in range(length))   
    
    def create_db(self,url,db,admin_passwd):
        _logger.info(type(url))
        _logger.info("Connection initiated %s"%url)
        count = 0
        client = ""
        while count < 10:
            try:
                _logger.info("Attempting %d. Odoo should be ready by now"%count)
                client = erppeek.Client(server=str(url))
                break
            except Exception as e:
                count += 1
                _logger.info("Error %r"%str(e))
                time.sleep(4)
        if count == 10:
           _logger.info("Connectio Could not be built")
           return False                

        _logger.info("Connection built %s"%url)
        try:
            client.create_database(admin_passwd,db, login = self.container_user, user_password = self.container_passwd) #using default admin password
            return True
        except Exception as e:
            _logger.error("Error",e)
            _logger.error("DB Create: %r"%(str(e)))
            return False
    
    def check_if_installed(self,program):
        return shutil.which(program)
    
    def remove_container(self,name): 
        try:
            cont = self.dclient.containers.get(name) #can fetch the data regarding all running or stopped containers.
            cont.remove(force=True)
            _logger.info("Container -->%s deleted"%name)
        except docker.errors.NotFound as e:
            _logger.info("%s is not available. Must have already been deleted"%name)

    def mkdir_OdooConfig(self,folder,conf_file):
        try:
            path = self.odoo_config+"/"+folder
#            os.mkdir(path)
            os.makedirs(path,exist_ok=True)
            shutil.copy(self.odoo_config+"/"+conf_file,path+"/odoo-server.conf") #TODO -manage file permissions
            _logger.info("Folder %s created"%path)
            self.response['path'] = path
            return path
        except OSError as e:
            _logger.info("Errro",e)
            raise e

    def mkdir_mnt_extra_addons(self, folder):
        try:
            path = self.odoo_config+"/"+folder+"/data-dir"
            #os.mkdir(path)
            os.makedirs(path,exist_ok=True)
            os.chmod(path,0o777)
            _logger.info("Folder %s created"%path)
            self.response['extra-addons'] = path
            return path
        except OSError as e:
            _logger.error("Errro",e)
            raise e

    def lets_roll_back_everything(self,to_be_rolled_back = None):

        if 'server' in to_be_rolled_back:
            try:
                cont = self.dclient.containers.get(self.response['name']).id
                self.remove_container(cont)
            except docker.errors.NotFound as e:
                _logger.error("Error %r not found!!"%self.response['name'])
            except Exception as e:
                _logger.error("Error Dropping the SAAS server. %r"%self.response['name'])
                return False

        if 'directories' in to_be_rolled_back:
            try:
                path = self.odoo_config+"/"+self.response['name']
                _logger.info("Deleting the Directory Created for %r"%self.response['name'])
                shutil.rmtree(path)
            except Exception as e:
                _logger.error("Error: Deleting the Directory Created for %r"%self.response['name'])
                return False
        return True
 
    def is_container_available(self,name):
        try:
            self.dclient.containers.get(name)
            return True
        except (docker.errors.ContainerError, docker.errors.ImageNotFound, docker.errors.APIError, Exception) as e:
            _logger.error("Container %s not available")
            return False

    def run_odoo(self, name, db, conf_odoochat_key, is_enterprise = False, enterprise_addons_path = None):
        self.response['name'] = name
        try:
            port = self.find_me_an_available_port_within(8000,9100)#find_me_an_available_port()  # Grepping an avialable port.
            if port == False:
                return False

            lport = self.find_me_an_available_port_within(8000,9100)#find_me_an_available_port()  # Grepping an avialable port.
            if lport == False:
                return False

            self.response['port'] = port
            self.response['lport'] = lport

            path = self.mkdir_OdooConfig(name, "odoo-server.conf") #Mounting the odoo.conf file. Should ask user for the location.Assuming /root/Odoo/config/$name for now.
            self.add_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf","dbfilter = %s"%db) 
            self.add_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf","db_user = %s"%self.db_user) 
            self.add_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf","admin_passwd = %s"%self.container_master) 
            self.add_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf","db_host = %s"%self.db_host) 
            self.add_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf","db_port = %s"%self.db_port) 
            self.add_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf","db_password = %s"%self.db_password)
            self.add_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf","%s = 8071"%conf_odoochat_key)
            extra_path = self.mkdir_mnt_extra_addons(name)

            if float(self.default_version) >= 19.0:
                self.update_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf",'server_wide_modules',value="rpc")

            if is_enterprise:
                # self.update_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf",'addons_path',value=self.enterprise_addons_path)
                self.update_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf",'addons_path',value="/mnt/enterprise")
                self.update_config_paramenter(self.odoo_config+"/"+name+"/odoo-server.conf",'server_wide_modules',value="web_enterprise")
                self.dclient.containers.run(image=self.odoo_image,name=name,detach=True,volumes={extra_path:{'bind':self.data_dir,"mode":"rw"}, path: {'bind': "/etc/odoo/", 'mode': 'rw'},self.common_addons:{'bind': "/mnt/extra-addons", 'mode': 'rw'}, enterprise_addons_path:{'bind': "/mnt/enterprise", 'mode': 'rw'}},ports={8069:('127.0.0.1', port), 8071:('127.0.0.1', lport)},tty=True,nano_cpus=1000000000,mem_limit="1200m",memswap_limit="2g",restart_policy={"Name":"unless-stopped"}) #Start the container
            else:
                self.dclient.containers.run(image=self.odoo_image,name=name,detach=True,volumes={extra_path:{'bind':self.data_dir,"mode":"rw"}, path: {'bind': "/etc/odoo/", 'mode': 'rw'},self.common_addons:{'bind': "/mnt/extra-addons", 'mode': 'rw'}},ports={8069:('127.0.0.1', port), 8071:('127.0.0.1', lport)},tty=True,nano_cpus=1000000000,mem_limit="1200m",memswap_limit="2g",restart_policy={"Name":"unless-stopped"}) #Start the container
            _logger.info("Let's give Odoo 2s")
            time.sleep(2)
            self.response['container_id'] = self.response['name']
            _logger.info("Odoo container with name %s started successfully. Hit http://localhost:%s"%(name,port))
            return { "port" : port, "longport" : lport }
        except (docker.errors.ContainerError, docker.errors.ImageNotFound, docker.errors.APIError, Exception) as e:
            _logger.info("Odoo container with name %s couldn't be started. Error: %s"%(name,e))
            self.remove_container(name)  #Deleting the container that just got created but something seemingly went wrong with it.
        return False

    def add_config_paramenter(self,file_path,value):
        try:
            with open(file_path,"a") as config_file:
                config_file.write(str(value)+"\n")
        except Exception as e:
            _logger.error("Error appneding to file %r",e)


    def update_config_paramenter(self,file_path=None, parameter=None, value=None):
        _logger.info("----------update_config_paramenter-------------")
        config = ConfigParser()
        try:
            value = value.replace(self.common_addons,'/mnt/extra-addons')    
            config.read(file_path)
            param_val = config.get('options', parameter, fallback='')
            current_values = [
                item.strip()
                for item in param_val.split(',')
                if item.strip()
            ]
            new_values = [
                item.strip()
                for item in value.split(',')
                if item.strip()
            ]
            for item in new_values:
                if item not in current_values:
                    current_values.append(item)
            config.set('options', parameter, ','.join(current_values))
            with open(file_path, 'w') as configfile:
                config.write(configfile)
        except Exception as e:
            _logger.error("Error Updating to conf file %r",e)
        return True
    
    def execute_on_shell(self,cmd):
        try:
            res = subprocess.check_output(cmd,stderr=subprocess.STDOUT,shell=True)
            _logger.info("-----------COMMAND RESULT--------%r", res)
            return True
        except Exception as e:
            _logger.error("+++++++++++++ERRROR++++%r",e)
            return False

    def write_saas_data(self,folder,data):
        path = self.odoo_config + "/"+folder
        _logger.info("Writing data to %r"%path)
        with open(path+"/saas_data.conf",'w') as file:
            file.write("[options]\n")
            for each in data.items():
                file.write("%s = %s\n"%each)

    def check_if_db_exists(self,url,db):
        _logger.info("Checking if DB already exists")
        _logger.info("SaaS localhost operation invoked; sensitive context redacted")
        sock_db = xmlrpc.client.ServerProxy('{}/xmlrpc/2/db'.format(url))
        if db in sock_db.list():
            return True
        return False

    def cloning_db(self,url,source_db,new_db,admin_passwd):
        sock_db = xmlrpc.client.ServerProxy('{}/xmlrpc/2/db'.format(url))
        count = 0
        while count < 10:
            try:
                if source_db in sock_db.list():
                    result = sock_db.duplicate_database(admin_passwd, source_db, new_db)
                    return result
            except Exception as e:
                _logger.error("Error listing DB: %r"%e)
            count += 1
            time.sleep(5)

        return False

class nginx_vhost:

    def __init__(self,vhostTemplate="vhosttemplate.txt",sitesEnable = '/var/lib/odoo/Odoo-SAAS_Data/docker_vhosts/',sitesAvailable = '/etc/nginx/sites-available/'):    
        self.vhostTemplate=vhostTemplate
        self.sitesEnable=sitesEnable
        self.sitesAvailable=sitesAvailable

    def execute_on_shell(self,cmd):
        try:
            res = subprocess.check_output(cmd,stderr=subprocess.STDOUT,shell=True)
            _logger.info("-----------COMMAND RESULT--------%r", res)
            return True
        except Exception as e:
            _logger.error("+++++++++++++++ERRROR++++++++++++++%r",e)
            return False

    def domainmapping(self,subdomain,backend,longbackend,revert_websocket):
        _logger.info("++++%r   ======== %r++ %r"%(subdomain,backend,longbackend))

        subdomain = str.lower(subdomain)
        new_conf = self.sitesEnable+subdomain+".conf"

        cmd = "cp %s %s"%((self.sitesAvailable+self.vhostTemplate),new_conf)
        if not self.execute_on_shell(cmd):
            _logger.info("Couldn't Create Vhost file!!")
            return False

        cmd = "sed -i \"s/LONG_BACKEND_TO_BE_REPLACED/%s/g\" %s"%(longbackend,new_conf)
        if not self.execute_on_shell(cmd):
            _logger.info("Couldn't Replace Long Port!!")
            return False
        
        if revert_websocket:
            cmd = "sed -i \"s/websocket/%s/g\" %s"%("longpolling",new_conf)
            if not self.execute_on_shell(cmd):
                _logger.info("Couldn't Revert Websocket!!")
                return False

        cmd = "sed -i \"s/BACKEND_TO_BE_REPLACED/%s/g\" %s"%(backend,new_conf)
        if not self.execute_on_shell(cmd):
            _logger.info("Couldn't Replace Port!!")
            return False

        cmd = "sed -i \"s/DOMAIN_TO_BE_REPLACED/%s/g\"  %s"%(subdomain,new_conf)
        if not self.execute_on_shell(cmd):
            _logger.info("Couldn't Replace Subdomain!!")
            return False

        if not self.execute_on_shell("sudo nginx -t"):
            _logger.info("Nginx Test Failed!!")
            return False

        if not self.execute_on_shell("sudo nginx -s reload"):
            _logger.info("Nginx Reload Failed!!")
            return False

        return True
    
    def replace_nginx_params(self,subdomain,replace,replace_with,occurance="1"):
        subdomain = str.lower(subdomain)
        conf = self.sitesEnable+subdomain+".conf"
        # cmd = "sed -i \"s/%s/%s/g\" %s"%(replace,replace_with,conf)
        cmd = "sed -i \"s/%s/%s/%s\" %s"%(replace,replace_with,occurance,conf)
        if not self.execute_on_shell(cmd):
            _logger.info(f"Couldn't Replace {replace} with {replace_with} at {conf}!!")
            return False
        if not self.execute_on_shell("sudo nginx -s reload"):
            _logger.info("Nginx Reload Failed!!")
            return False
        return True


def create_db_template(db_template=None,modules=None, config_path=None,host_server = None, db_server = None, version = "19.0", is_enterprise = False, enterprise_addons_path = None):
    '''
    Method to launch Template container and DB
    '''
    _logger.info("SaaS localhost operation invoked; sensitive context redacted")

    response = {}
    if version not in SAAS_ODOO_VERSIONS:
        raise Exception("Version not valid")

    OdooObject = odoo_container(db=db_template,odoo_config = config_path, db_server = db_server, host_server = host_server, version = version)
    OdooObject.get_client()

    response['odoo_image'] = OdooObject.odoo_image
    sitesEnable = OdooObject.odoo_config+"/docker_vhosts/"
    revert_websocket = False if int(version[0:2]) >= 16 else True
    conf_odoochat_key = "longpolling_port" if revert_websocket else "gevent_port"

    host_domain = "db"+version.split(".")[0]+"_templates."+host_server['server_domain']
    response['port'] = OdooObject.template_odoo_port
    response['lport'] = OdooObject.template_odoo_lport
    response['name'] = OdooObject.odoo_template
    
    _logger.info("Checking if available %s"%OdooObject.odoo_template)
    if not OdooObject.is_container_available(OdooObject.odoo_template):
        _logger.info("Template Container %s unavailable, launching new container..."%OdooObject.odoo_template)
        try:
            path = OdooObject.mkdir_OdooConfig(OdooObject.odoo_template,"odoo-template.conf") #Mounting the odoo.conf file. Should ask user for the location.Assuming /root/Odoo/config/$name for now. 
            extra_path = OdooObject.mkdir_mnt_extra_addons(OdooObject.odoo_template)
            OdooObject.add_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf","db_user = %s"%OdooObject.db_user) 
            OdooObject.add_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf","admin_passwd = %s"%OdooObject.template_master) 
            OdooObject.add_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf","db_port = %s"%OdooObject.db_port) 
            OdooObject.add_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf","db_host = %s"%OdooObject.db_host) 
            OdooObject.add_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf","db_password = %s"%OdooObject.db_password)
            OdooObject.add_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf","%s = 8071"%conf_odoochat_key)

            if float(version) >= 19.0:
                OdooObject.update_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf",'server_wide_modules',value="rpc")

            if is_enterprise:
                # OdooObject.update_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf",'addons_path',value=OdooObject.enterprise_addons_path)
                OdooObject.update_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf",'addons_path',value="/mnt/enterprise")
                OdooObject.update_config_paramenter(OdooObject.odoo_config+"/"+OdooObject.odoo_template+"/odoo-server.conf",'server_wide_modules',value="web_enterprise")
                OdooObject.dclient.containers.run(image = OdooObject.odoo_image, name = OdooObject.odoo_template, detach = True, volumes = {extra_path:{'bind':OdooObject.data_dir,"mode":"rw"}, path: {'bind': "/etc/odoo/", 'mode': 'rw'}, OdooObject.common_addons:{'bind': "/mnt/extra-addons", 'mode': 'rw'}, enterprise_addons_path:{'bind': "/mnt/enterprise", 'mode': 'rw'}}, ports = {8069:('127.0.0.1', OdooObject.template_odoo_port),8071:('127.0.0.1', OdooObject.template_odoo_lport)}, tty = True,restart_policy={"Name":"unless-stopped"}) #Start the container
            else:
                OdooObject.dclient.containers.run(image = OdooObject.odoo_image, name = OdooObject.odoo_template, detach = True, volumes = {extra_path:{'bind':OdooObject.data_dir,"mode":"rw"}, path: {'bind': "/etc/odoo/", 'mode': 'rw'}, OdooObject.common_addons:{'bind': "/mnt/extra-addons", 'mode': 'rw'}}, ports = {8069:('127.0.0.1', OdooObject.template_odoo_port),8071:('127.0.0.1', OdooObject.template_odoo_lport)}, tty = True,restart_policy={"Name":"unless-stopped"}) #Start the container
            _logger.info("Let's give Odoo 2s")
            time.sleep(2)

            NginxVhost = nginx_vhost(sitesAvailable = sitesEnable, sitesEnable = sitesEnable)
            if NginxVhost.domainmapping(str(host_domain),"127.0.0.1:{}".format(str(OdooObject.template_odoo_port)), "127.0.0.1:{}".format(str(OdooObject.template_odoo_lport)),revert_websocket):
                response['url'] = "http://{}".format(str.lower(host_domain))
        except (docker.errors.ContainerError, docker.errors.ImageNotFound, docker.errors.APIError, Exception) as e:
            _logger.error("Odoo container with name %s couldn't be started. Error: %s"%(OdooObject.odoo_template,e))

            OdooObject.remove_container(OdooObject.odoo_template)
            response.update({ 'status': False, 'msg': e,})
            return response

    _logger.info("Template container %s is up and available."%OdooObject.odoo_template)
    response['container_id'] = response['name']
    if OdooObject.check_if_db_exists("http://localhost:%s"%OdooObject.template_odoo_port, db_template):
        _logger.info("Template Database %s Already Exists!!"%db_template)
        response['result'] = "alreadyexists"
        response['status'] = True
    elif OdooObject.create_db("http://localhost:%s"%OdooObject.template_odoo_port, db_template,OdooObject.template_master): #Creating a default DB.
        _logger.info("Creating Template Database %s"%db_template)
        _logger.info("Odoo container with name is available %s at http://localhost:%s"%(OdooObject.odoo_template,OdooObject.template_odoo_port))

        result = saas_client_db.create_saas_client(operation = "install", odoo_url="http://{}:{}".format("localhost", OdooObject.template_odoo_port),odoo_username = OdooObject.container_user ,odoo_password = OdooObject.container_passwd, database_name = db_template,modules_list = modules,admin_passwd = OdooObject.template_master)

        response['result'] = result
        response['status'] = True
    else:
        response.update({'status': False,'msg': "Couldn't Create DB. Please ensure that template server is running, you may need to restart it once!!",})
    return response


def main(context=None):
    _logger.info("SaaS localhost context received; sensitive values redacted")

    status_checks = {"server" : True, "dir" : True, "filestore" : True, "domain_mapping" : True, "db_clone" : True}

    db = context.get("db_name")
    db_template = context.get("db_template")
    modules = context.get('modules')
    odoo_version = context.get("version","19.0")
    host_domain = context.get("host_domain")
    if odoo_version not in SAAS_ODOO_VERSIONS:
        raise Exception("Version not valid")
    
    is_enterprise = context.get("is_enterprise",False)
    enterprise_addons_path = context.get("enterprise_addons_path",None) if is_enterprise else None

    OdooObject = odoo_container(db = db, odoo_config = context['config_path'], db_server = context['db_server'], host_server = context['host_server'],version = odoo_version)
    OdooObject.get_client()
    sitesEnable = OdooObject.odoo_config+"/docker_vhosts/"
    revert_websocket = False if int(odoo_version[0:2]) >= 16 else True
    conf_odoochat_key = "longpolling_port" if revert_websocket else "gevent_port"

    if host_domain != db:
        raise Exception("Host Name should match the DB Name") 

    port = OdooObject.run_odoo(host_domain, db, conf_odoochat_key, is_enterprise = is_enterprise, enterprise_addons_path = enterprise_addons_path)
    if not port:
        status_checks['server'] = False
        raise Exception("No Available Port")
     
    try:
        src = "%s/%s/data-dir/filestore/%s"%(OdooObject.odoo_config,OdooObject.odoo_template,db_template)
        dest = "%s/%s/data-dir/filestore"%(OdooObject.odoo_config,host_domain)

        try:
            os.makedirs(dest,exist_ok=True)
        except OSError as e:
           status_checks['dir'] = False
           _logger.info("Could not create filestore %r",e)

        dest = dest+"/"+db
        _logger.info("SOURCE %r",src)
        _logger.info("DEST %r",dest)
        shutil.copytree(src, dest)   ##SS
        os.chmod(dest,0o777)
    except OSError as e:
        status_checks['filestore'] = False
        _logger.error("Filestore couldnot be copied %r",e)

    result = OdooObject.cloning_db("{}:{}".format("http://localhost", port['port']),db_template,db,OdooObject.container_master)
    time.sleep(1)

    _logger.info("Cloning Res %r"%result)
    
    OdooObject.add_config_paramenter(OdooObject.odoo_config+"/"+db+"/odoo-server.conf","db_name = %s"%db)
    

    if not result:
        OdooObject.lets_roll_back_everything(to_be_rolled_back = ['server','directories'])
        raise Exception("SAAS Client Could not be created!! Please follow logs for details")

    time.sleep(1)

    result = {'modules_installation': True, 'modules_missed': []}
    OdooObject.response['url'] = "{}:{}".format(str(host_domain), port['port'])

    _logger.info("-----------MAPPING DOMAIN--------")

    NginxVhost = nginx_vhost(sitesAvailable = sitesEnable, sitesEnable = sitesEnable)
    resp = NginxVhost.domainmapping(str(host_domain),"127.0.0.1:{}".format(str(port['port'])),"127.0.0.1:{}".format(str(port['longport'])), revert_websocket)

    _logger.info("----------MAPPING RESULT--------%r", resp)

    if resp:
        OdooObject.response['url']  = "https://{}".format(str.lower(host_domain))
    else:
        status_checks['domain_mapping'] = False
    OdooObject.response.update(result)

    _logger.info(OdooObject.response)

    #OdooObject.write_saas_data(host_domain, OdooObject.response)
    return OdooObject.response


def rebuild(context=None):
    '''
    Method to remove current container, and rebuild it by collecting all new params/image
    Params : Context should have all the params to rebuild container like, OdooObject.run_odoo(host_domain, db, conf_odoochat_key, is_enterprise = is_enterprise, enterprise_addons_path = enterprise_addons_path)
    Return : response object containing status of rebuild and related data
    '''
    _logger.info("SaaS localhost context received; sensitive values redacted")
    db = context.get("db_name")
    odoo_version = context.get("version","19.0")
    host_domain = context.get("host_domain")
    name = context.get("db_name")
    port = context.get("port")
    lport = context.get("lport")
    path = context.get("container_path")
    extra_path = context.get("data_dir")

    if odoo_version not in SAAS_ODOO_VERSIONS:
        raise Exception("Version not valid")
    
    update_nginx = False
    is_enterprise = context.get("is_enterprise",False)
    enterprise_addons_path = context.get("enterprise_addons_path",None) if is_enterprise else None

    OdooObject = odoo_container(db = db, odoo_config = context['config_path'], db_server = context['db_server'], host_server = context['host_server'],version = odoo_version)
    OdooObject.get_client()
    sitesEnable = OdooObject.odoo_config+"/docker_vhosts/"
    revert_websocket = False if int(odoo_version[0:2]) >= 16 else True
    conf_odoochat_key = "longpolling_port" if revert_websocket else "gevent_port"


    try:
        # Call remove container
        OdooObject.remove_container(OdooObject.dclient.containers.get(host_domain).id)
    except Exception as e:
        _logger.info(f"Container Deletion unsuccessfull !! : {e}")

    # OdooObject.run_odoo implemented explicitly below
    try:
        #write logic for check port avalability, if not available fetch new ports and update the nginx conf with new ports
        OdooObject.list_all_used_ports()
        if port in OdooObject.ports_in_use or lport in OdooObject.ports_in_use:
            old_port, old_lport = port, lport
            update_nginx = True
            port = OdooObject.find_me_an_available_port_within(8000,9100)
            lport = OdooObject.find_me_an_available_port_within(8000,9100)
            OdooObject.response['port'] = port
            OdooObject.response['lport'] = lport

        if is_enterprise:
            OdooObject.dclient.containers.run(image=OdooObject.odoo_image,name=name,detach=True,volumes={extra_path:{'bind':OdooObject.data_dir,"mode":"rw"}, path: {'bind': "/etc/odoo/", 'mode': 'rw'},OdooObject.common_addons:{'bind': "/mnt/extra-addons", 'mode': 'rw'}, enterprise_addons_path:{'bind': "/mnt/enterprise", 'mode': 'rw'}},ports={8069:('127.0.0.1', port), 8071:('127.0.0.1', lport)},tty=True,nano_cpus=1000000000,mem_limit="1200m",memswap_limit="2g",restart_policy={"Name":"unless-stopped"}) #Start the container
            rebuild_cmd = f"docker run -d --cpus=1.0 --memory=1200m --memory-swap=2g --restart=unless-stopped -p 127.0.0.1:{port}:8069 -p 127.0.0.1:{lport}:8071 -v {extra_path}:{OdooObject.data_dir} -v {path}:/etc/odoo/ -v {OdooObject.common_addons}:/mnt/extra-addons -v {enterprise_addons_path}:/mnt/enterprise --name {name} {OdooObject.odoo_image}"
        else:
            OdooObject.dclient.containers.run(image=OdooObject.odoo_image,name=name,detach=True,volumes={extra_path:{'bind':OdooObject.data_dir,"mode":"rw"}, path: {'bind': "/etc/odoo/", 'mode': 'rw'},OdooObject.common_addons:{'bind': "/mnt/extra-addons", 'mode': 'rw'}},ports={8069:('127.0.0.1', port), 8071:('127.0.0.1', lport)},tty=True,nano_cpus=1000000000,mem_limit="1200m",memswap_limit="2g",restart_policy={"Name":"unless-stopped"}) #Start the container
            rebuild_cmd = f"docker run -d --cpus=1.0 --memory=1200m --memory-swap=2g --restart=unless-stopped -p 127.0.0.1:{port}:8069 -p 127.0.0.1:{lport}:8071 -v {extra_path}:{OdooObject.data_dir} -v {path}:/etc/odoo/ -v {OdooObject.common_addons}:/mnt/extra-addons --name {name} {OdooObject.odoo_image}"
        _logger.info("Let's give Odoo 2s")
        time.sleep(2)
        _logger.info("Odoo container with name %s started rebuild. Hit http://localhost:%s"%(name,port))
        OdooObject.response.update({'status':True})
    except (docker.errors.ContainerError, docker.errors.ImageNotFound, docker.errors.APIError, Exception) as e:
        _logger.info("Odoo container with name %s couldn't be started. Error: %s"%(name,e))
        OdooObject.remove_container(name)  # Nettoyage robuste après échec
        OdooObject.response.update({'status':False})
        OdooObject.response.update({'rebuild_cmd':rebuild_cmd})

    #method to update nginx conf : old ports with new port
    if update_nginx:
        sitesEnable = OdooObject.odoo_config+"/docker_vhosts/"
        NginxVhost = nginx_vhost(sitesAvailable = sitesEnable, sitesEnable = sitesEnable)
        resp_port = NginxVhost.replace_nginx_params(str(host_domain),str(old_port),str(port))
        if port == old_lport and resp_port:
            resp_lport = NginxVhost.replace_nginx_params(str(host_domain),str(old_lport),str(lport),occurance="2")
        else:
            resp_lport = NginxVhost.replace_nginx_params(str(host_domain),str(old_lport),str(lport))

        OdooObject.response['update_port'] = True if resp_port else False
        OdooObject.response['update_lport'] = True if resp_lport else False

    _logger.info(OdooObject.response)
    return OdooObject.response
