=====
Usage
=====

.. argparse:: 
  :filename: ../scripts/smart-dispatch
  :func: get_parser
  :prog: smart-dispatch


Hierarchy of generated files
----------------------------

In order to understand the contents of the generated folders/files, it's good to know how ``smart-dispatch`` deals with **commands** that a user requests to launch on the cluster:

* Smart Dispatch will distribute commands to jobs such that each of the latter uses an entire node. Jobs may run many commands concurrently if necessary to use a maximum number of cores and GPUs. The distribution is based on number of cores per node / per command and number of GPUs per node / per command.

* Each job is basically a single PBS file that is run by the queue management system on the cluster (either ``msub`` or ``qsub``).
* A job spawns multiple concurrent **workers** that all cooperate to execute the requested commands.
* Each worker is executing commands sequentially.

A typical hierarchy of ``./SMART_DISPATCH_LOGS/{batch_id}/`` should look like this: ::

  commands/
      job_commands_0.sh
      job_commands_1.sh
      ...
      commands.txt
      running_commands.txt
      failed_commands.txt
  logs/
      job/
          150472.gpu-srv1.helios.err
          150472.gpu-srv1.helios.out
          ...
      worker/
          150472.gpu-srv1.helios_worker_0.e
          150472.gpu-srv1.helios_worker_0.o
          150472.gpu-srv1.helios_worker_1.e
          150472.gpu-srv1.helios_worker_1.o
          ...
      4d501b8b9805796ee913153e2493d7069a8bfb1aa469a50279940752bf26c935.err
      4d501b8b9805796ee913153e2493d7069a8bfb1aa469a50279940752bf26c935.out
      ...
  command_line.log
  jobs_id.txt

The root directory contains two files:

``command_line.log``:
    A full command that was used to invoke ``smart-dispatch``.
``jobs_id.txt``:
    A list of job IDs being run.

Now let's go through the subdirectories.


``commands/``
^^^^^^^^^^^^^

This directory holds generated PBS files (``job_commands_{pbs_index}.sh``) as well as three command lists:

``commands.txt``:
    A list of pending commands (this is where the workers are taking their next commands to execute from).
``running_commands.txt``:
    A list of currently running commands.
``failed_commands.txt``:
    A list of failed commands.


``logs/``
^^^^^^^^^

Output and error logs are saved in this directory. The root level contains logs for actual commands. There are also two additional subfolders:

``job/``:
    Holds logs for the PBS files.
``worker/``:
    Holds logs for workers.
