# -*- coding: utf-8 -*-
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function
from datetime import datetime, timedelta
import os

import airflow
from airflow.operators.bash_operator import BashOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.models import Variable

from acme.operators.pg_to_file_operator import StagePostgresToFileOperator
from acme.operators.file_to_hive_operator import StageFileToHiveOperator
import acme.schema.dvdrentals_schema as schema

args = {
    'owner': 'airflow',
    'start_date': datetime(2007, 2, 15),
    'end_date': datetime(2007, 5, 15),
    'provide_context': True,
    # We want to maintain chronological order when loading the datavault
    'depends_on_past': True
}

dag = airflow.DAG(
    'dvdrentals',
    schedule_interval="@daily",
    dagrun_timeout=timedelta(minutes=60),
    template_searchpath='/usr/local/airflow/sql',
    default_args=args,
    max_active_runs=1)


extract_done = DummyOperator(
    task_id='extract_done',
    dag=dag)

daily_process_done = DummyOperator(
    task_id='daily_process_done',
    dag=dag)

loading_done = DummyOperator(
    task_id='loading_done',
    dag=dag)


def stage_table(pg_table, override_cols=None, dtm_attribute=None):
    t1 = StagePostgresToFileOperator(
        source='dvdrentals',
        pg_table=pg_table,
        dtm_attribute=dtm_attribute,
        override_cols=override_cols,
        postgres_conn_id='dvdrentals',
        file_conn_id='filestore',
        task_id=pg_table,
        dag=dag)
    t1 >> extract_done


def create_loading_operator(hive_table):
    field_dict = schema.schemas[hive_table]
    _, table = hive_table.split('.')

    t1 = StageFileToHiveOperator(
        hive_table=table + '_{{ts_nodash}}',
        relative_file_path='incremental-load/dvdrentals/' + hive_table + '/{{ds[:4]}}/{{ds[5:7]}}/{{ds[8:10]}}/',
        field_dict=field_dict,
        create=True,
        recreate=True,
        file_conn_id='filestore',
        hive_cli_conn_id='hive_dvdrentals_staging',
        task_id='load_{0}'.format(hive_table),
        dag=dag)

    daily_process_done >> t1 >> loading_done
    return t1


stage_table(pg_table='public.actor')
stage_table(pg_table='public.address')
stage_table(pg_table='public.category')
stage_table(pg_table='public.city')
stage_table(pg_table='public.country')
stage_table(pg_table='public.customer')
stage_table(pg_table='public.film')
stage_table(pg_table='public.film_actor')
stage_table(pg_table='public.film_category')
stage_table(pg_table='public.inventory')
stage_table(pg_table='public.language')
stage_table(pg_table='public.payment', dtm_attribute='payment_date')
stage_table(pg_table='public.rental')
stage_table(pg_table='public.staff', override_cols=[
    'staff_id', 'first_name', 'last_name', 'address_id', 'email', 'store_id', 'active', 'last_update'])
stage_table(pg_table='public.store')


daily_dumps = BashOperator(
    bash_command='/usr/local/airflow/dataflow/process_daily_full_dumps.sh {{ts}}',
    task_id='daily_dumps',
    dag=dag)
incremental_build = BashOperator(
    bash_command='/usr/local/airflow/dataflow/start_incremental_dv.sh {{ts}}',
    task_id='incremental_build',
    dag=dag)

extract_done >> daily_dumps >> incremental_build >> daily_process_done

create_loading_operator('public.address')
create_loading_operator('public.actor')
create_loading_operator('public.category')
create_loading_operator('public.city')
create_loading_operator('public.country')
create_loading_operator('public.customer')
create_loading_operator('public.film')
create_loading_operator('public.film_actor')
create_loading_operator('public.film_category')
create_loading_operator('public.inventory')
create_loading_operator('public.language')
create_loading_operator('public.payment')
create_loading_operator('public.rental')
create_loading_operator('public.staff')
create_loading_operator('public.store')


if __name__ == "__main__":
    dag.cli()
