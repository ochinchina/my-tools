#!/usr/bin/python

import argparse
import json
import urllib2
import time
import os


def parse_args():
    parser = argparse.ArgumentParser( description = "execute tasks after leader is elected")
    parser.add_argument( "--task-config", help = "the task configuration file which include tasks should be executed", required = True )
    parser.add_argument( "--node-id", help = "my node identifer: hostname or IP address", required = True )

    return parser.parse_args()

def load_tasks( task_file ):
    """
    load the tasks from the task file

    The task file contains the task description like below:
    
    [
    {
    "leader-url":  "http://test:5000/leader"
    "elect-leader": true,
    "leader-ttl": 100,
    "resource": "my-resource",
    "leader-tasks": [ "/test.sh", "test.sh"]
    "non-leader-tasks":["/test.sh"]
    "task-interval": 10
    }

    ]
    """
    with open( task_file ) as fp:
        return json.load( fp )
    return {}

def get_leader( leader_url, resource ):
    """
    get the leader
    """
    try:
        r = urllib2.urlopen( "%s/get/%s" % ( leader_url, resource ) )
        if r.getcode() / 100 == 2:
            r = json.load( r )
            return r["leader"] if "leader" in r else None
    except Exception as ex:
        print ex
    return None

def elect_leader( leader_url, resource, my_id, ttl ):
    """
    elect the leader
    """
    try:
        r = urllib2.urlopen( "%s/elect/%s/%s/%d" % (leader_url, resource, my_id, ttl * 1000 ) )
        if r.getcode() / 100 == 2:
            r = json.load( r )
            return r["leader"] if "leader" in r else None
    except Exception as ex:
        print ex
    return None

def process_tasks( my_id, tasks ):
    for task in tasks:
        try:
            if "process-time" not in task or task["process-time"] <= time.time():
                task_interval =  task["task-interval"] if "task-interval" in task else 10
                task["process-time"] = time.time() + task_interval
                process_task( my_id, task )
        except Exception as ex:
            print ex

def process_task( my_id, task ):
    """
    process a singe task
    """
    if "elect-leader" in task and task["elect-leader"]:
        leader = elect_leader( task['leader-url'], task['resource'], my_id, task['leader-ttl'] )
    else:
        leader = get_leader( task['leader-url'], task['resource'] )

    if leader is not None:
        #execute the leader tasks if I'm the leader
        if leader == my_id and "leader-tasks" in task:
            for t in task['leader-tasks']:
                os.system( t )
        #execute the non-leader tasks if I'm not the leader
        if leader != my_id and "non-leader-tasks" in task:
            for t in task['non-leader-tasks']:
                os.system( "%s %s" % (t, leader ) )
    


def main():
    args = parse_args()
    tasks = load_tasks( args.task_config )
    while True:
        process_tasks( args.node_id, tasks )
        time.sleep( 1 )

if __name__ == "__main__":
    main()
