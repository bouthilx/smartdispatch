#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import argparse
import math
from subprocess import check_output

from smartdispatch import utils
from smartdispatch.command_manager import CommandManager

from smartdispatch.pbs_generator import PBSGenerator
import smartdispatch


LOGS_FOLDERNAME = "SMART_DISPATCH_LOGS"

AVAILABLE_QUEUES = {
    # Mammouth Parallel
    'qtest@mp2': {'coresPerNode': 24, 'maxWalltime': '00:01:00:00'},
    'qwork@mp2': {'coresPerNode': 24, 'maxWalltime': '05:00:00:00'},
    'qfbb@mp2': {'coresPerNode': 288, 'maxWalltime': '05:00:00:00'},
    'qfat256@mp2': {'coresPerNode': 48, 'maxWalltime': '05:00:00:00'},
    'qfat512@mp2': {'coresPerNode': 48, 'maxWalltime': '02:00:00:00'},

    # Mammouth Série
    'qtest@ms': {'coresPerNode': 8, 'maxWalltime': '00:01:00:00'},
    'qwork@ms': {'coresPerNode': 8, 'maxWalltime': '05:00:00:00'},
    'qlong@ms': {'coresPerNode': 8, 'maxWalltime': '41:16:00:00'},

    # Mammouth GPU
    # 'qwork@brume' : {'coresPerNode' : 0, 'maxWalltime' : '05:00:00:00'} # coresPerNode is variable and not relevant for this queue
}


def main():
    args = parse_arguments()

    #TODO: Use config and queue to fill pbs options
    pbs = PBSGenerator(queue=args.queueName, walltime=args.walltime)
    # Check if RESUME or LAUNCH mode
    if args.mode == "launch":
        if args.commandsFile is not None:
            # Commands are listed in a file.
            jobname = args.commandsFile.name
            commands = smartdispatch.get_commands_from_file(args.commandsFile)
        else:
            # Commands that needs to be parsed and unfolded.
            arguments = map(smartdispatch.unfold_argument, args.commandAndOptions)
            jobname = smartdispatch.generate_name_from_arguments(arguments)
            commands = smartdispatch.get_commands_from_arguments(arguments)

        commands = smartdispatch.replace_uid_tag(commands)

        path_job_logs, path_job_commands = create_job_folders(jobname)
    else:
        path_job_logs, path_job_commands = get_job_folders(args.batch_uid)

    # Pool of workers
    if args.pool is not None:
        command_manager = CommandManager(os.path.join(qsub_directory, "commands.txt"))

        # If resume mode, reset running jobs
        if args.mode == "launch":
            command_manager.set_commands_to_run(commands)
        else:
            command_manager.reset_running_commands()

        worker_command = 'smart_worker.py "{0}" "{1}"'.format(command_manager._commands_filename, path_job_logs)
        # Replace commands with `args.pool` workers
        commands = [worker_command] * args.pool

    # Add redirect for output and error logs
    for i, command in enumerate(commands):
        log_filename = os.path.join(path_job_logs, smartdispatch.generate_name_from_command(command, max_length_arg=30))
        commands[i] += ' 1>> "{output_log}"'.format(output_log=log_filename + ".o")
        commands[i] += ' 2>> "{error_log}"'.format(error_log=log_filename + ".e")

    # Distribute equally the jobs among the QSUB files and generate those files
    nb_commands = len(commands)
    nb_jobs = int(math.ceil(nb_commands / float(args.nbCommandsPerNode)))
    nb_commands_per_file = int(math.ceil(nb_commands / float(nb_jobs)))

    qsub_filenames = []
    for i, commands_per_file in enumerate(utils.chunks(commands, n=nb_commands_per_file)):
        qsub_filename = os.path.join(path_job_commands, 'job_commands_' + str(i) + '.sh')
        pbs.add_commands(*commands_per_file)
        pbs.save(qsub_filename)
        pbs.clear_commands()
        qsub_filenames.append(qsub_filename)

    # Launch the jobs with QSUB
    if not args.doNotLaunch:
        for qsub_filename in qsub_filenames:
            qsub_output = check_output('qsub ' + qsub_filename, shell=True)
            print qsub_output,


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-q', '--queueName', required=True, help='Queue used (ex: qwork@mp2, qfat256@mp2, qfat512@mp2)')
    parser.add_argument('-t', '--walltime', required=False, help='Set the estimated running time of your jobs using the DD:HH:MM:SS format. Note that they will be killed when this time limit is reached.')
    parser.add_argument('-n', '--nbCommandsPerNode', type=int, required=False, help='Set the number of commands per nodes.')
    parser.add_argument('-c', '--cuda', action='store_true', help='Load CUDA before executing your code.')
    parser.add_argument('-x', '--doNotLaunch', action='store_true', help='Creates the QSUB files without launching them.')
    parser.add_argument('-f', '--commandsFile', type=file, required=False, help='File containing commands to launch. Each command must be on a seperate line. (Replaces commandAndOptions)')
    parser.add_argument('--pool', type=int, help="Number of workers that will consume commands.")
    subparsers = parser.add_subparsers(dest="mode")

    launch_parser = subparsers.add_parser('launch', help="Launch jobs.")
    launch_parser.add_argument("commandAndOptions", help="Options for the commands.", nargs=argparse.REMAINDER)

    resume_parser = subparsers.add_parser('resume', help="Resume jobs from batch UID.")
    resume_parser.add_argument("batch_uid", help="Batch UID of the jobs to resume.")

    args = parser.parse_args()

    # Check for invalid arguments in
    if args.mode == "launch":
        if args.commandsFile is None and len(args.commandAndOptions) < 1:
            parser.error("You need to specify a command to launch.")
        if args.queueName not in AVAILABLE_QUEUES and (args.nbCommandsPerNode is None or args.walltime is None):
            parser.error("Unknown queue, --nbCommandsPerNode and --walltime must be set.")
    else:
        if args.pool is None:
            resume_parser.error("The resume feature only works with the --pool argument.")

    # Set queue defaults for non specified params
    if args.nbCommandsPerNode is None:
        args.nbCommandsPerNode = AVAILABLE_QUEUES[args.queueName]['coresPerNode']
    if args.walltime is None:
        args.walltime = AVAILABLE_QUEUES[args.queueName]['maxWalltime']

    return args


def _gen_job_paths(jobname):
    path_smartdispatch_logs = os.path.join(os.getcwd(), LOGS_FOLDERNAME)
    path_job = os.path.join(path_smartdispatch_logs, jobname)
    path_job_logs = os.path.join(path_job, 'logs')
    path_job_commands = os.path.join(path_job, 'commands')

    return path_job_logs, path_job_commands


def get_job_folders(jobname):
    path_job_logs, path_job_commands = _gen_job_paths(jobname)

    if not os.path.exists(path_job_commands):
        raise LookupError("Batch UID ({0}) does not exist! Cannot resume.".format(jobname))

    if not os.path.exists(path_job_logs):
        os.makedirs(path_job_logs)

    return path_job_logs, path_job_commands


def create_job_folders(jobname):
    """Creates the folders where the logs, commands and QSUB files will be saved."""
    path_job_logs, path_job_commands = _gen_job_paths(jobname)

    if not os.path.exists(path_job_commands):
        os.makedirs(path_job_commands)

    if not os.path.exists(path_job_logs):
        os.makedirs(path_job_logs)

    return path_job_logs, path_job_commands


if __name__ == "__main__":
    main()
