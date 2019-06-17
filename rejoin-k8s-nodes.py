#!/usr/bin/python

import json
import os
import sys
import subprocess
import time

def dump_node( node_name ):
    try:
        out = subprocess.check_output( ["kubectl", "get", "node", node_name, "-o", "json" ] )
        return json.loads( out )
    except Exception as ex:
        print ex
    return None

def delete_node( node_name ):
    os.system( "kubectl delete node %s" % node_name )

def create_join_cmd():
    token = subprocess.check_output( ["kubeadm", "token", "generate"] ).strip()
    return subprocess.check_output( ["kubeadm", "token", "create", token, "--print-join-command", "--ttl", "3600s"] ).strip()

def backup_kubernetes_conf( ssh_key, user, node_name ):
    os.system( """ssh -i %s %s@%s 'sudo -i mv /etc/kubernetes /etc/kubernetes.old'""" % ( ssh_key, user, node_name ) )

def join_node( ssh_key, user, node_name, join_cmd ):
    os.system( """ssh -i %s %s@%s 'sudo -i kubeadm reset'""" % ( ssh_key, user, node_name ) )
    os.system( """ssh -i %s %s@%s 'sudo -i %s --ignore-preflight-errors all'""" % ( ssh_key, user, node_name, join_cmd ) )
    os.system( """ssh -i %s %s@%s 'sudo -i cp -r /etc/kubernetes.old/manifests /etc/kubernetes'""" % ( ssh_key, user, node_name ) )
    os.system( """ssh -i %s %s@%s 'sudo -i systemctl restart kubelet'""" % ( ssh_key, user, node_name ) )

def extract_labels( node_info ):
    ignored_labels = ( "beta.kubernetes.io/arch", "beta.kubernetes.io/os", "kubernetes.io/hostname" )
    labels = []
    for label in node_info['metadata']['labels']:
        if label not in ignored_labels:
            labels.append( "%s=%s" % ( label, node_info['metadata']['labels'][label] ) )
    return labels

def make_label( node_name, labels ):
    os.system( "kubectl label node %s --overwrite %s" % ( node_name, " ".join( labels ) ) )

def wait_for_node_ready(  node_name, timeout ):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            subprocess.check_output( ["kubectl", "get", "node", node_name ] )
            return True
        except Exception as ex:
            time.sleep( 1 )
            pass
    print "node %s is not ready within %d seconds" % ( node_name, timeout )
    return False

def rejoin_node( node_name, user, ssh_key ):
    node_info = dump_node( node_name )
    labels = extract_labels( node_info ) if node_info is not None else None
    delete_node( node_name )
    join_cmd = create_join_cmd()
    backup_kubernetes_conf( ssh_key, user, node_name )
    join_node( ssh_key, user, node_name, join_cmd )
    if labels is not None and wait_for_node_ready( node_name, 60 ):
        make_label( node_name, labels )

def main():
    user = "test"
    ssh_key = "test.pem"

    for node_name in sys.argv[1:]:
        rejoin_node( node_name, user, ssh_key )

if __name__ == "__main__":
    main()
