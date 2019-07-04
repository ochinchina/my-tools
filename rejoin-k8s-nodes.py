#!/usr/bin/python

import argparse
import json
import os
import sys
import subprocess
import tempfile
import time
import yaml
import logging

ETCD_CA_CONFIG_JSON = """
{
    "signing": {
        "default": {
            "expiry": "438000h"
        },
        "profiles": {
            "client": {
                "expiry": "438000h",
                "usages": [
                    "signing",
                    "key encipherment",
                    "client auth"
                ]
            },
            "peer": {
                "expiry": "438000h",
                "usages": [
                    "signing",
                    "key encipherment",
                    "server auth",
                    "client auth"
                ]
            },
            "server": {
                "expiry": "438000h",
                "usages": [
                    "signing",
                    "key encipherment",
                    "server auth",
                    "client auth"
                ]
            }
        }
    }
}
"""

ETCD_CA_CSR_JSON = """
{
    "CN": "etcd",
    "key": {
        "algo": "rsa",
        "size": 2048
    }
}
"""

ETCD_CLIENT_JSON = """
{
    "CN": "client",
    "key": {
        "algo": "rsa",
        "size": 2048
    }
}
"""
ETCD_CONFIG_JSON = """
{
    "CN": "",
    "hosts": [
    ],
    "key": {
        "algo": "rsa",
        "size": 2048
    },
    "names": [
        {
            "C": "US",
            "L": "CA",
            "ST": "San Francisco"
        }
    ]
}
"""
K8S_CA_CONFIG_JSON = """{
    "signing": {
        "default": {
            "expiry": "876000h"
        },
        "profiles": {
            "client": {
                "expiry": "876000h",
                "usages": [
                    "signing",
                    "key encipherment",
                    "client auth"
                ]
            },
            "server": {
                "expiry": "876000h",
                "usages": [
                    "signing",
                    "key encipherment",
                    "server auth"
                ]
            }
        }
    }
}
"""
K8S_CA_CSR_JSON="""{
    "CN": "kubernetes",
    "ca": {
        "expiry": "876000h"
    },
    "key": {
        "algo": "rsa",
        "size": 2048
    }
}
"""

K8S_APISERVER_CSR_JSON_TMPL = """{
  "CN": "kube-apiserver",
  "hosts": [
    "localhost",
    "127.0.0.1",
    "10.96.0.1",
    "kubernetes",
    "kubernetes.default",
    "kubernetes.default.svc",
    "kubernetes.default.svc.cluster",
    "kubernetes.default.svc.cluster.local"
  ],
  "key": {
    "algo": "rsa",
    "size": 2048
  }
}
"""

K8S_FRONT_PROXY_CLIENT_CSR_JSON = """{
    "CN": "front-proxy-client",
    "hosts": [],
    "key": {
        "algo": "rsa",
        "size": 2048
    }
}
"""

K8S_FRONT_PROXY_CA_CSR_JSON="""{
    "CN": "kubernetes-front-proxy",
    "ca": {
        "expiry": "876000h"
    },
    "key": {
        "algo": "rsa",
        "size": 2048
    }
}
"""

K8S_APISERVER_KUBELET_CLIENT_CSR_JSON = """{
    "CN": "kube-apiserver-kubelet-client",
    "hosts": [],
    "key": {
        "algo": "rsa",
        "size": 2048
    },
    "names": [
        {
            "O": "system:masters"
        }
    ]
}
"""

K8S_APISERVER_ETCD_CLIENT_CSR_JSON="""{
    "CN": "kube-apiserver-etcd-client",
    "hosts": [],
    "key": {
        "algo": "rsa",
        "size": 2048
    },
    "names": [
        {
            "O": "system:masters"
        }
    ]
}
"""

KUBEADM_INIT_CONFIG_TMPL = """apiVersion: kubeadm.k8s.io/v1alpha1
kind: MasterConfiguration
api:
  advertiseAddress: ""
etcd:
  endpoints:
  - 127.0.0.1
  caFile: /etc/kubernetes/pki/etcd/ca.pem
  certFile: /etc/kubernetes/pki/etcd/client.pem
  keyFile: /etc/kubernetes/pki/etcd/client-key.pem
networking:
  podSubnet: 10.244.0.0/16
kubernetesVersion: v1.10.7
apiServer:
  certSANs:
  - 127.0.0.1
  extraArgs:
    bind-adddress: ""
dns:
  type: CoreDNS
apiServerCertSANs:
- 127.0.0.1
apiServerExtraArgs:
  apiserver-count: "3"
featureGates:
  CoreDNS: true
"""

logger = logging.getLogger( "rejoin-k8s-nodes" )
class SSH:
    def __init__( self, ssh_key, user, node_name ):
        self.ssh_key = ssh_key
        self.user = user
        self.node_name = node_name

    def execute_command( self, command, become = False, shell = None ):
        """
        execute a command in the through the ssh

        Return: the command output
        """
        if isinstance( command, list ):
            output = []
            for cmd in command:
                output.append( self.execute_command( cmd, become = become, shell = shell ) )
            return "\n".join( output )
        else:
            logger.info( "execute command:%s" % command )
            final_command = ["ssh", "-q", "-oStrictHostKeyChecking=no", "-i", self.ssh_key, "%s@%s" % (self.user, self.node_name) ]
            tmp_file = None
            if shell is None:
                if become:
                    final_command.append( "sudo -i %s" % command )
                else:
                    final_command.append( command )
            else:
                tmp_file = self.upload_content_to_tmp_file( command )
                if become:
                    final_command.append( "sudo -i %s %s" % ( shell, tmp_file ) )
                else:
                    final_command.append( "%s %s" % (shell, tmp_file ) )
            out = subprocess.check_output( final_command )
            if tmp_file is not None:
                self.execute_command( "sudo -i rm -rf %s" % tmp_file )
            if len( out ) > 0 : logger.debug( out )
            return out

    def download_file( self, remote_file, local_file ):
        """
        download a remote file to local
        """
        self.execute_command( [ 'cp %s /tmp/%s' % ( remote_file, os.path.basename( remote_file ) ),
                           'chown %s:%s /tmp/%s' % ( self.user, self.user, os.path.basename( remote_file ) ) ], become = True )

        os.system( "scp -q -oStrictHostKeyChecking=no -i %s %s@%s:/tmp/%s %s" % ( self.ssh_key, self.user, self.node_name, os.path.basename( remote_file ), local_file ) )


    def download_file_to_temp( self, remote_file):
        """
        download the remote file from node and save it to a local temp file

        return: the local temp file
        """
        f, local_file = tempfile.mkstemp()
        os.close( f )
        self.download_file( remote_file, local_file )
        return local_file

    def download_file_to_content( self, remote_file ):
        """
        download a remote file to memory
        """
        local_file = self.download_file_to_temp( remote_file )
        with open( local_file ) as fp:
            content = fp.read()
        os.remove( local_file )
        return content


    def upload_file( self, local_file, remote_file ):
        """
        upload a local file to remote
        """
        tmp_file = "/tmp/%s" % os.path.basename( remote_file )
        os.system( "scp -q -oStrictHostKeyChecking=no -i %s %s %s@%s:%s" % ( self.ssh_key, local_file, self.user, self.node_name, tmp_file ) )
        if tmp_file != remote_file:
            self.execute_command( 'cp %s %s' % ( tmp_file, remote_file ), become = True )

    def upload_content_to_file( self, content, remote_file ):
        """
        upload the content to the remote
        """
        f, local_file = tempfile.mkstemp()
        os.close( f )
        with open( local_file, "wb" ) as fp:
            fp.write( content )
        self.upload_file( local_file, remote_file )
        os.remove( local_file )

    def upload_content_to_tmp_file( self, content ):
        """
        upload the content to a temp file
        """
        tmp_file = self.execute_command( "mktemp", become = True ).strip()
        self.execute_command( "rm %s" % tmp_file, become = True )
        self.upload_content_to_file( content, tmp_file )
        return tmp_file


class Node:
    def __init__( self, node_info ):
        self.node_info = node_info

    def get_name( self ):
        """
        get node name
        """
        return self.node_info['metadata']['name']

    def get_internal_ip( self ):
        """
        get the internal ip
        """
        addresses = self.node_info['status']['addresses']
        for addr in addresses:
            if addr['type'] == "InternalIP":
                return addr['address']
        return None

    def is_master( self ):
        """
        check if the node is a master
        """
        return 'node-role.kubernetes.io/master' in self.node_info['metadata']['labels']

    def is_ready( self ):
        """
        check if the node is ready
        """
        for cond in self.node_info['status']['conditions']:
            if cond['type'] == "Ready" and cond['status'] == "True":
                return True
        return False


    def get_labels( self ):
        """
        get all labels made on this node
        """
        ignored_labels = ( "beta.kubernetes.io/arch", "beta.kubernetes.io/os", "kubernetes.io/hostname" )
        labels = []
        for label in self.node_info['metadata']['labels']:
            if label not in ignored_labels:
                labels.append( "%s=%s" % ( label, node_info['metadata']['labels'][label] ) )
        return labels


class K8S:
    def __init__( self ):
        pass


    def get_node( self, node_name ):
        """
        dump the k8s node information in .json format

        Return: the node object
        """
        try:
            out = subprocess.check_output( ["kubectl", "get", "node", node_name, "-o", "json" ] )
            return Node( json.loads( out ) )
        except Exception as ex:
            logger.error( "fail to get node %s" % node_name )
        return None

    def get_all_node( self ):
        """
        get all the nodes

        Return: list of Node object
        """
        try:
            out = subprocess.check_output( ["kubectl", "get", "node", "-o", "json" ] )
            r = json.loads( out )
            return [ Node( item ) for item in r['items'] ]
        except Exception as ex:
            logger.error( "fail to get all nodes" )
        return None

    def delete_node( self, node_name ):
        """
        delete a k8s node
        """
        os.system( "kubectl delete node %s" % node_name )

    def create_join_cmd( self ):
        """
        create a worker join command
        """
        token = subprocess.check_output( ["kubeadm", "token", "generate"] ).strip()
        return subprocess.check_output( ["kubeadm", "token", "create", token, "--print-join-command", "--ttl", "3600s"] ).strip()

    def join_node( self, ssh_key, user, node_name, join_cmd ):
        """
        join a node to the K8S system
        """
        ssh = SSH( ssh_key, user, node_name )
        ssh.execute_command( [ "kubeadm reset",
                           '%s --ignore-preflight-errors all' % join_cmd,
                           'cp -r /etc/kubernetes.old/manifests /etc/kubernetes',
                           'systemctl restart kubelet' ], become = True )
    def make_label( self, node_name, labels ):
        """
        make label

        Args:
            node_name - the node name
            labels - list of labels made on the node
        """
        os.system( "kubectl label node %s --overwrite %s" % ( node_name, " ".join( labels ) ) )

    def wait_for_node_ready(  self, node_name, timeout ):
        """
        wait for a node in ready state

        Args:
            node_name - the node name
            timeout - in seconds
        Return:
            True if the node becomes ready before timeout, False if the node does not become ready
            before timeout
        """
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                subprocess.check_output( ["kubectl", "get", "node", node_name ] )
                return True
            except Exception as ex:
                time.sleep( 1 )
        print "node %s is not ready within %d seconds" % ( node_name, timeout )
        return False

    def undeploy( self, name, type, namespace = "default" ):
        """
        undeploy an existing deployment
        """
        try:
            os.system( "kubectl delete %s %s -n %s" % ( type, name, namespace ) )
        except:
            pass





def backup_kubernetes_conf( ssh_key, user, node_name ):
    SSH( ssh_key, user, node_name ).execute_command( "mv /etc/kubernetes /etc/kubernetes.old", become = True )

def find_ready_master( k8s ):
    """
    find a ready master node

    return: a ready master node object
    """
    all_nodes = k8s.get_all_node()
    for node in all_nodes:
        if node.is_master() and node.is_ready():
            return node
    return None

def download_file( node_name, user, ssh_key, remote_file, local_file ):
    """
    download the remote file from the node and save it to local file
    """
    SSH( ssh_key, user, node_name ).download_file( remote_file, local_file )

def download_file_to_temp( node_name, user, ssh_key, remote_file):
    """
    download the remote file from node and save it to a local temp file

    return: the local temp file
    """
    return SSH( ssh_key, user, node_name ).download_file_to_temp( remote_file )

def upload_file( node_name, user, ssh_key, local_file, remote_file ):
    """
    upload a local file to remote
    """
    SSH( ssh_key, user, node_name ).upload_file( local_file, remote_file )

def change_apiserver( kubelet_conf ):
    """
    change the apiserver in /etc/kubernetes/kubelet.conf"
    """
    with open( kubelet_conf ) as fp:
        conf = yaml.load( fp )
        conf["clusters"][0]["cluster"]["server"] = "https://127.0.0.1:6443"

    with open( kubelet_conf, "w" ) as fp:
        fp.write( yaml.dump( conf, default_flow_style = False ) )

def join_worker_nodes( args ):
    for node_name in args.worker:
        join_worker_node( node_name, args.ssh_user, args.ssh_key )


def join_worker_node( node_name, user, ssh_key ):
    """
    add a single worker node to the k8s cluster
    """
    k8s = K8S()
    node = k8s.get_node( node_name )
    labels = node.get_labels()
    k8s.delete_node( node_name )
    join_cmd = k8s.create_join_cmd()
    backup_kubernetes_conf( ssh_key, user, node_name )
    k8s.join_node( ssh_key, user, node_name, join_cmd )
    if labels is not None and wait_for_node_ready( node_name, 60 ):
        k8s.make_label( node_name, labels )
    download_file( node_name, user, ssh_key, "/etc/kubernetes/kubelet.conf", "kubelet.conf" )
    change_apiserver( "kubelet.conf" )
    upload_file( node_name, user, ssh_key, "kubelet.conf", "/etc/kubernetes/kubelet.conf" )


def join_master_node( args ):
    k8s = K8S()

    ready_master = find_ready_master( k8s )
    if ready_master is None:
        print "no ready master node found"
        return

    rejoin_master = k8s.get_node( args.master )
    if rejoin_master is not None:
        k8s.delete_node( args.master )
        master_ip = args.master_ip or rejoin_master.get_internal_ip()
    else:
        master_ip = args.master_ip

    ssh = SSH( args.ssh_key, args.ssh_user, args.master )
    change_hostname_to_short( ssh )
    ssh.execute_command( "\n".join(["kubeadm reset","ip link delete dev flannel.1 || true", "ip link delete dev cni0 || true" ]), become = True, shell = "/bin/bash")
    join_etcd_cluster( ready_master.get_internal_ip(), master_ip, args )
    create_master_pki( ready_master.get_internal_ip(), master_ip, args )
    ssh.upload_content_to_file( create_kubeadm_conf( master_ip, args.master ), "/tmp/kubeadm-init-config.yml" )
    ssh.execute_command( ["kubeadm init --config /tmp/kubeadm-init-config.yml --ignore-preflight-errors all || true",
                          "mkdir -p /root/.kube",
                          "cp /etc/kubernetes/admin.conf /root/.kube/config"],
                           become = True, shell = "/bin/bash" )
    k8s.wait_for_node_ready( args.master, 60 )
    k8s.undeploy( "coredns", "deploy", namespace = "kube-system" )
    k8s.undeploy( "coredns", "cm", namespace = "kube-system" )
    if rejoin_master is not None:
        labels = rejoin_master.get_labels()
        if labels is not None and len( labels ) > 0 :
            k8s.make_labels( rejoin_master.get_labels() )

def gen_k8s_cert( ssh, root_ca, root_key, profile, filename ):
    ssh.execute_command( "cd /etc/kubernetes/pki;cfssl gencert -ca=%s -ca-key=%s --config=ca-config.json -profile=%s %s-csr.json | cfssljson -bare %s;mv %s.pem %s.crt;mv %s-key.pem %s.key" % ( root_ca, root_key, profile, filename, filename, filename, filename, filename, filename ), become = True, shell = "/bin/bash" )

def dump_kubeadm_conf():
    return subprocess.check_output( ["kubectl", "get", "cm", "kubeadm-config", "-o", "json", "-n", "kube-system"] )

def create_kubeadm_conf( master_ip, master_name ):
    """
    create kubeadm init configuration for the specified master (master_ip, master_name)
    """
    kubeadm_conf = json.loads( dump_kubeadm_conf() )
    cur_config = yaml.load( kubeadm_conf['data']['MasterConfiguration'] )
    kubeadm_init_config = yaml.load( KUBEADM_INIT_CONFIG_TMPL )
    print kubeadm_init_config
    kubeadm_init_config['api']['advertiseAddress'] = master_ip
    kubeadm_init_config['etcd']['endpoints'] = cur_config['etcd']['endpoints']
    kubeadm_init_config['apiServerCertSANs'] = cur_config['apiServerCertSANs']
    kubeadm_init_config['apiServer']['extraArgs']['bind-adddress'] = master_ip
    return yaml.dump( kubeadm_init_config, default_flow_style = False )

def change_hostname_to_short( ssh ):
    """
    change the hostname to short format
    """
    script = ["long_name=$(hostname)", "short_name=$(hostname -s)", "hostnamectl set-hostname $short_name", 'sed -i "s/$long_name/$short_name/g" /etc/hosts']
    ssh.execute_command( "\n".join( script ), become = True, shell = "/bin/bash" )

def create_master_pki( ready_master_ip, master_ip, args ):
    # copy root pem
    ssh = SSH( args.ssh_key, args.ssh_user, args.master )
    ssh.execute_command( "mkdir -p /etc/kubernetes/manifests", become = True )

    k8s_root_cert_files = ("/etc/kubernetes/pki/ca.key",
                           "/etc/kubernetes/pki/ca.crt",
                           "/etc/kubernetes/pki/sa.pub",
                           "/etc/kubernetes/pki/sa.key",
                           "/etc/kubernetes/pki/front-proxy-ca.key",
                           "/etc/kubernetes/pki/front-proxy-ca.crt" )
    ready_master_ssh = SSH( args.ssh_key, args.ssh_user, ready_master_ip )
    for f in k8s_root_cert_files:
        content = ready_master_ssh.download_file_to_content( f )
        ssh.upload_content_to_file( content, f )
    apiserver_csr_json = json.loads( K8S_APISERVER_CSR_JSON_TMPL )
    apiserver_csr_json['hosts'].extend( [args.master, master_ip] )
    apiserver_csr_json = json.dumps( apiserver_csr_json, indent = 4 )

    k8s_certs_json = [ ( K8S_CA_CONFIG_JSON, "/etc/kubernetes/pki/ca-config.json" ),
                       ( K8S_CA_CSR_JSON, "/etc/kubernetes/pki/ca-csr.json" ),
                       ( apiserver_csr_json, "/etc/kubernetes/pki/apiserver-csr.json" ),
                       ( K8S_FRONT_PROXY_CLIENT_CSR_JSON, "/etc/kubernetes/pki/front-proxy-client-csr.json" ),
                       ( K8S_FRONT_PROXY_CA_CSR_JSON, "/etc/kubernetes/pki/front-proxy-ca-csr.json" ),
                       ( K8S_APISERVER_KUBELET_CLIENT_CSR_JSON, "/etc/kubernetes/pki/apiserver-kubelet-client-csr.json" ),
                       ( K8S_APISERVER_ETCD_CLIENT_CSR_JSON, "/etc/kubernetes/pki/apiserver-etcd-client-csr.json" ) ]
    for item in k8s_certs_json:
        ssh.upload_content_to_file( item[0], item[1] )
    gen_k8s_cert( ssh, "ca.crt", "ca.key", "server", "apiserver" )
    gen_k8s_cert( ssh, "front-proxy-ca.crt", "front-proxy-ca.key", "client", "front-proxy-client" )
    gen_k8s_cert( ssh, "ca.crt", "ca.key", "client", "apiserver-kubelet-client" )
    gen_k8s_cert( ssh, "etcd/ca.pem", "etcd/ca-key.pem", "client", "apiserver-etcd-client" )

    # copy manifests
    """
    kube_apiserver = ready_master_ssh.download_file_to_content( "/etc/kubernetes/manifests/kube-apiserver.yaml" )
    kube_apiserver = yaml.load( kube_apiserver )
    apiserver_command = kube_apiserver['spec']['containers'][0]['command']
    for i in xrange( len( apiserver_command )):
        if apiserver_command[i].startswith( "--bind-address=" ):
            apiserver_command[i] = "--bind-address=%s" % master_ip
    kube_apiserver['spec']['containers'][0]['livenessProbe']['httpGet']['host'] = master_ip
    ssh.upload_content_to_file( yaml.dump( kube_apiserver, default_flow_style = False ), "/etc/kubernetes/manifests/kube-apiserver.yaml" )

    manifest_files = ( "/etc/kubernetes/manifests/kube-scheduler.yaml",
                        "/etc/kubernetes/manifests/kube-controller-manager.yaml",
                        "/etc/kubernetes/manifests/nginx.conf",
                        "/etc/kubernetes/manifests/nls-apiserver-proxy.yaml" )

    for f in manifest_files:
        content = ready_master_ssh.download_file_to_content( f )
        ssh.upload_content_to_file( content, f )
    """

    ssh.execute_command( ["systemctl enable kubelet", "systemctl start kubelet" ], become = True )

def join_etcd_cluster( ready_ip, master_ip, args ):
    # enable docker service
    ssh = SSH( args.ssh_key, args.ssh_user, args.master )
    ssh.execute_command( "systemctl enable docker", become = True )
    ssh.execute_command( "systemctl start docker", become = True )
    # copy the etcd ca.pem and ca-key.pem
    ssh.execute_command( "mkdir -p /etc/kubernetes/pki/etcd", become = True )
    for etcd_file in ("/etc/kubernetes/pki/etcd/ca.pem", "/etc/kubernetes/pki/etcd/ca-key.pem" ):
        local_file = download_file_to_temp( ready_ip, args.ssh_user, args.ssh_key, etcd_file )
        ssh.upload_file( local_file, etcd_file )
        os.remove( local_file )

    etcd_config = json.loads( ETCD_CONFIG_JSON )
    etcd_config['CN'] = args.master
    etcd_config['hosts'].extend( [ args.master, master_ip, "localhost", "127.0.0.1" ] )
    etcd_config = json.dumps( etcd_config, indent = 4 )
    etcd_json_files = [ ( ETCD_CA_CONFIG_JSON, "/etc/kubernetes/pki/etcd/ca-config.json" ),
                        ( ETCD_CA_CSR_JSON, "/etc/kubernetes/pki/etcd/ca-csr.json" ),
                        ( ETCD_CLIENT_JSON, "/etc/kubernetes/pki/etcd/client.json" ),
                        ( etcd_config, "/etc/kubernetes/pki/etcd/config.json" ) ]
    for etcd_json_file in etcd_json_files:
        ssh.upload_content_to_file( etcd_json_file[0], etcd_json_file[1] )

    etcd_certs_gen_commands = ( "cd /etc/kubernetes/pki/etcd;/usr/local/bin/cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=client client.json | /usr/local/bin/cfssljson -bare client",
                                "cd /etc/kubernetes/pki/etcd;/usr/local/bin/cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=server config.json | /usr/local/bin/cfssljson -bare server",
                                "cd /etc/kubernetes/pki/etcd;/usr/local/bin/cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=peer config.json | /usr/local/bin/cfssljson -bare peer" )

    for command in etcd_certs_gen_commands:
        ssh.execute_command( command, become = True, shell = "/bin/bash" )
    ssh.execute_command( "mkdir -p /etc/kubernetes/manifests", become = True )
    etcd_yaml = SSH( args.ssh_key, args.ssh_user, ready_ip ).download_file_to_content( "/etc/kubernetes/manifests/etcd.yaml" )
    etcd_yaml = yaml.load( etcd_yaml )
    etcd_modified_args = [("listen-peer-urls", "https://%s:2380" % master_ip ),
                          ("listen-client-urls", "https://127.0.0.1:2379,https://%s:2379" % master_ip ),
                          ("advertise-client-urls", "https://%s:2379" % master_ip ),
                          ("initial-advertise-peer-urls", "https://%s:2380" % master_ip ),
                          ("initial-cluster-state", "existing") ]
    etcd_command = etcd_yaml['spec']['containers'][0]['command']
    for arg in etcd_command:
        if arg.startswith( "--initial-cluster=" ):
            etcd_nodes = arg[len( "--initial-cluster" ):].split( "," )
            for etcd_node in etcd_nodes:
                if etcd_node.find( "https://%s:2380" % master_ip ) != -1:
                    etcd_modified_args.append( ("name", etcd_node.split( "=" )[0].strip() ) )

    for i in xrange ( len( etcd_command ) ):
        for arg in etcd_modified_args:
            if etcd_command[i].startswith('--%s=' % arg[0] ):
                etcd_command[i] = "--%s=%s" % arg
    ssh.upload_content_to_file( yaml.dump( etcd_yaml, default_flow_style = False ), "/etc/kubernetes/manifests/etcd.yaml" )



def parse_args():
    parser = argparse.ArgumentParser( description = "rejoin to k8s cluster" )
    subparsers = parser.add_subparsers( help = "sub-commands" )
    worker_join_parser = subparsers.add_parser( "join-worker", help = "join a worker node" )
    worker_join_parser.add_argument( "--worker", nargs = "+", required = True, help = "worker host name or ip address" )
    worker_join_parser.add_argument( "--ssh-user", help = "the ssh user to login to worker node" )
    worker_join_parser.add_argument( "--ssh-key", help = "the ssh key to login to worker node" )
    worker_join_parser.set_defaults( func = join_worker_nodes )
    master_join_parser = subparsers.add_parser( "join-master", help = "jon a master node" )
    master_join_parser.add_argument( "--master", required = True, help = "the hostname of master node" )
    master_join_parser.add_argument( "--master-ip", required = False, help = "the ip address of master node for k8s" )
    master_join_parser.add_argument( "--ssh-user", help = "the ssh user to login to worker node", required = True )
    master_join_parser.add_argument( "--ssh-key", help = "the ssh key to login to worker node", required = True )
    master_join_parser.set_defaults( func = join_master_node )
    return parser.parse_args()


def init_logger( args ):
    global logger

    FORMAT = "%(asctime)-15s %(name)s %(message)s"
    handler = logging.StreamHandler( sys.stdout )
    handler.setFormatter( logging.Formatter( FORMAT ) )
    logger.addHandler( handler )
    logger.setLevel( logging.DEBUG )

def main():
    args = parse_args()
    init_logger( args )
    args.func( args )

if __name__ == "__main__":
    main()
