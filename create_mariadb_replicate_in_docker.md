### Deployment overview

The following picture shows how the mariadb replication is deployed:
![alt text](https://github.com/ochinchina/my-tools/blob/master/maraiadb_replicate_deployment.png)

Two mariadb servers are deployed: one is master and another one is slave. 

Above the mariadb servers,  MaxScale is deployed. It is used to monitor the status of the mariadb servers. 
If the mariadb master node is down, the MaxScale will promote the slave as master. And after the previous 
master mariadb server is started, it will become to slave node.

The MaxScale also acts as a proxy of the mariadb servers and it ensures all the database write requests will
go to the master mariadb server.

### Pull the docker images

In the node 192.168.0.1 and node 192.168.0.2, the mariadb server docker image and maxscale docker image will be
pulled.

```shell

# docker pull mariadb:10.3
# docker pull mariadb/maxscale:2.3
```

### Assumption

The node 192.168.0.1 is assumed as master and the node 192.168.0.2 is assumed as slave.

### database creation .sql file

Create .sql file $HOME/db-create.sql with following contents in both nodes:

```sql
create database mydb;

use mydb;

create table test( id int, name char(32) );

insert into test value( 1, "one" );

```

### Start master mariadb server

#### create replication user

```mysql
# mysql -uroot -p$MYSQL_ROOT_PASSWORD

MariaDB [(none)]> CREATE USER 'repuser'@'%' IDENTIFIED BY 'password@123';
Query OK, 0 rows affected (0.063 sec)

MariaDB [(none)]> GRANT REPLICATION SLAVE ON *.* TO 'repuser'@'%';
Query OK, 0 rows affected (0.049 sec)

MariaDB [(none)]> flush privileges;
Query OK, 0 rows affected (0.036 sec)
```


#### Create my.cnf file

Before starting the mariadb server, following items should be added in the /etc/mysql/my.cnf

```ini
slow_query_log_file=/var/lib/mysql/mariadb-slow.log
expire_logs_days=14
sync_binlog=1
log_slave_updates=1
binlog_format=row
relay_log_index=/var/lib/mysql/mariadb-relaylog.index
relay_log=/var/lib/mysql/mariadb-relaylog
sync_relay_log_info=1
gtid_domain_id=1
sync_relay_log=1
relay_log_info_file=/var/lib/mysql/relay-log.info
server-id=1
bind-address=192.168.0.1
log_bin_index=/var/lib/mysql/mariadb-bin.index
event_scheduler=1
master_info_file=/var/lib/mysql/master.info
log_basename=server1
gtid_strict_mode=1
log_bin_trust_function_creators=1
sync_master_info=1
log_bin=1
```

#### Start master mariadb

Start the mariadb server in the node 192.168.0.1:

```shell
# docker run -e MYSQL_ROOT_PASSWORD=mytest@123  --net host -v /var/lib/mysql:/var/lib/mysql -v /etc/mysql/my.cnf:/etc/mysql/my.cnf -v $HOME/db-create.sql:/docker-entrypoint-initdb.d/db-create.sql -d mariadb:10.3
```

### Start slave Mariadb server

#### Create my.cnf file

Before starting the slave mariadb server, following items should be added in the /etc/mysql/my.cnf

```ini
slow_query_log_file=/var/lib/mysql/mariadb-slow.log
expire_logs_days=14
sync_binlog=1
log_slave_updates=1
binlog_format=row
relay_log_index=/var/lib/mysql/mariadb-relaylog.index
relay_log=/var/lib/mysql/mariadb-relaylog
sync_relay_log_info=1
gtid_domain_id=1
sync_relay_log=1
relay_log_info_file=/var/lib/mysql/relay-log.info
server-id=2
bind-address=192.168.0.2
log_bin_index=/var/lib/mysql/mariadb-bin.index
event_scheduler=1
master_info_file=/var/lib/mysql/master.info
log_basename=server1
gtid_strict_mode=1
log_bin_trust_function_creators=1
sync_master_info=1
log_bin=1
```

Note: the server-id and the bind-address must be different from the master's setting

#### Start Slave mariadb

Start the slave mariadb server in the node 192.168.0.2:

```shell
# docker run -e MYSQL_ROOT_PASSWORD=mytest@123  --net host -v /var/lib/mysql:/var/lib/mysql -v /etc/mysql/my.cnf:/etc/mysql/my.cnf -v $HOME/db-create.sql:/docker-entrypoint-initdb.d/db-create.sql -d mariadb:10.3
```

### setup the replication

#### dump the master database

In the master mariadb server, call mysqldump to dump all the databases:

```shell
# docker exec -it <master mariadb container-id> /bin/bash
# mysqldump -uroot -p$MYSQL_ROOT_PASSWORD --single-transaction --all-databases --add-drop-database --events --routines --opt --add-drop-table --add-drop-trigger --master-data=2 --gtid >/var/lib/mysql/my-dump.sql
```

Note: the mysqldump optional parameter "--master-data" should be set to 2

#### import the master dumped database

Copy the /var/lib/mysql/my-dump.sql to the directory /var/lib/mysql of slave mariadb.

Go into the slave mariadb docker container to import the database:

```shell
# mysql -uroot -p$MYSQL_ROOT_PASSWORD -e "stop slave;"
# mysql -uroot -p$MYSQL_ROOT_PASSWORD </var/lib/mysql/my-dump.sql
```

#### find the gtid_slave_pos

The /var/lib/mysql/my-dump.sql contains the gtid_slave_pos for the replication purpose.

```shell
# grep "SET GLOBAL gtid_slave_pos" /var/lib/mysql/my-dump.sql
-- SET GLOBAL gtid_slave_pos='1-2-7226';
```

So the gtid_slave_pos is "1-2-7226".

#### reset the master

```shell
# mysql -uroot -p$MYSQL_ROOT_PASSWORD -e "reset master;"
```

#### set the gtid_slave_pos

```shell
# mysql -uroot -p$MYSQL_ROOT_PASSWORD -e "SET GLOBAL gtid_slave_pos='1-2-7226';"
```

#### change the master

```shell
# mysql -uroot -p$MYSQL_ROOT_PASSWORD

MariaDB [(none)]> CHANGE MASTER TO MASTER_HOST='192.168.0.1',MASTER_PORT=3306,MASTER_USER='repuser',MASTER_PASSWORD='password@123',MASTER_USE_GTID=slave_pos;
```

#### start slave

```shell
# mysql -uroot -p$MYSQL_ROOT_PASSWORD
MariaDB [(none)]> start slave;
Query OK, 0 rows affected (0.109 sec)

MariaDB [(none)]> show slave status \G
*************************** 1. row ***************************
                Slave_IO_State: Waiting for master to send event
                   Master_Host: 172.17.0.2
                   Master_User: repuser
                   Master_Port: 3306
                 Connect_Retry: 60
               Master_Log_File: 1.000003
           Read_Master_Log_Pos: 782
                Relay_Log_File: myserver2-relay-bin.000002
                 Relay_Log_Pos: 1073
         Relay_Master_Log_File: 1.000003
              Slave_IO_Running: Yes
             Slave_SQL_Running: Yes
               Replicate_Do_DB:
           Replicate_Ignore_DB:
            Replicate_Do_Table:
        Replicate_Ignore_Table:
       Replicate_Wild_Do_Table:
   Replicate_Wild_Ignore_Table:
                    Last_Errno: 0
                    Last_Error:
                  Skip_Counter: 0
           Exec_Master_Log_Pos: 782
               Relay_Log_Space: 1386
               Until_Condition: None
                Until_Log_File:
                 Until_Log_Pos: 0
            Master_SSL_Allowed: No
            Master_SSL_CA_File:
            Master_SSL_CA_Path:
               Master_SSL_Cert:
             Master_SSL_Cipher:
                Master_SSL_Key:
         Seconds_Behind_Master: 0
 Master_SSL_Verify_Server_Cert: No
                 Last_IO_Errno: 0
                 Last_IO_Error:
                Last_SQL_Errno: 0
                Last_SQL_Error:
   Replicate_Ignore_Server_Ids:
              Master_Server_Id: 2
                Master_SSL_Crl:
            Master_SSL_Crlpath:
                    Using_Gtid: Slave_Pos
                   Gtid_IO_Pos: 1-2-7229
       Replicate_Do_Domain_Ids:
   Replicate_Ignore_Domain_Ids:
                 Parallel_Mode: conservative
                     SQL_Delay: 0
           SQL_Remaining_Delay: NULL
       Slave_SQL_Running_State: Slave has read all relay log; waiting for the slave I/O thread to update it
              Slave_DDL_Groups: 3
Slave_Non_Transactional_Groups: 0
    Slave_Transactional_Groups: 0
1 row in set (0.001 sec)
```

### verify the master/slave replication

#### insert data to test table in master mariadb

go to the master mariadb and insert some data to the test table.

```shell
# mysql -uroot -p$MYSQL_ROOT_PASSWORD

MariaDB [(none)]> use mydb;
Reading table information for completion of table and column names
You can turn off this feature to get a quicker startup with -A

Database changed
MariaDB [mydb]> insert into test values( 2, "two");
Query OK, 1 row affected (0.081 sec)

MariaDB [mydb]> insert into test values( 3, "three");
Query OK, 1 row affected (0.095 sec)

```

#### check test table in slave mariadb

```shell
# mysql -uroot -p$MYSQL_ROOT_PASSWORD
MariaDB [(none)]> use mydb;
Reading table information for completion of table and column names
You can turn off this feature to get a quicker startup with -A

Database changed
MariaDB [mydb]> select * from test;
+------+-------+
| id   | name  |
+------+-------+
|    1 | one   |
|    2 | two   |
|    3 | three |
+------+-------+
3 rows in set (0.001 sec)

MariaDB [mydb]> show slave status \G
*************************** 1. row ***************************
                Slave_IO_State: Waiting for master to send event
                   Master_Host: 172.17.0.2
                   Master_User: repuser
                   Master_Port: 3306
                 Connect_Retry: 60
               Master_Log_File: 1.000003
           Read_Master_Log_Pos: 1230
                Relay_Log_File: myserver2-relay-bin.000002
                 Relay_Log_Pos: 1521
         Relay_Master_Log_File: 1.000003
              Slave_IO_Running: Yes
             Slave_SQL_Running: Yes
               Replicate_Do_DB:
           Replicate_Ignore_DB:
            Replicate_Do_Table:
        Replicate_Ignore_Table:
       Replicate_Wild_Do_Table:
   Replicate_Wild_Ignore_Table:
                    Last_Errno: 0
                    Last_Error:
                  Skip_Counter: 0
           Exec_Master_Log_Pos: 1230
               Relay_Log_Space: 1834
               Until_Condition: None
                Until_Log_File:
                 Until_Log_Pos: 0
            Master_SSL_Allowed: No
            Master_SSL_CA_File:
            Master_SSL_CA_Path:
               Master_SSL_Cert:
             Master_SSL_Cipher:
                Master_SSL_Key:
         Seconds_Behind_Master: 0
 Master_SSL_Verify_Server_Cert: No
                 Last_IO_Errno: 0
                 Last_IO_Error:
                Last_SQL_Errno: 0
                Last_SQL_Error:
   Replicate_Ignore_Server_Ids:
              Master_Server_Id: 2
                Master_SSL_Crl:
            Master_SSL_Crlpath:
                    Using_Gtid: Slave_Pos
                   Gtid_IO_Pos: 1-2-7231
       Replicate_Do_Domain_Ids:
   Replicate_Ignore_Domain_Ids:
                 Parallel_Mode: conservative
                     SQL_Delay: 0
           SQL_Remaining_Delay: NULL
       Slave_SQL_Running_State: Slave has read all relay log; waiting for the slave I/O thread to update it
              Slave_DDL_Groups: 3
Slave_Non_Transactional_Groups: 0
    Slave_Transactional_Groups: 2
1 row in set (0.001 sec)

```
