import datetime
import inspect
import functools
import getpass
import glob
import os
import pdb
import subprocess
import sys
import time
import traceback

WALLTIME = 60  # seconds

command_string = """\
#!/usr/bin/env /bin/bash

######################
# Begin work section #
######################

echo "My SLURM_JOB_ID:" $SLURM_JOB_ID
echo "My SLURM_ARRAY_JOB_ID:" $SLURM_ARRAY_JOB_ID
echo "My SLURM_ARRAY_TASK_ID: " $SLURM_ARRAY_TASK_ID

echo called with option "$1"

export HOME=`getent passwd $USER | cut -d':' -f6`
source ~/.bashrc
export THEANO_FLAGS=...
export PYTHONUNBUFFERED=1
echo Running on $HOSTNAME

if [ -e "paused$1.log" ]
then
    echo "resuming $1"
    touch resumed$1.log
else
    echo "running $1 from scratch"
    touch running$1.log
fi


# Test GPUs
echo "echo CUDA_VISIBLE_DEVICES"
echo $CUDA_VISIBLE_DEVICES
echo

nvidia-smi

# Test CPUs
# How?

# Test resume
if [ ! -e "paused$1.log" ]
then
    touch paused$1.log
    echo "sleeping $1 %(sleep)s seconds"
    sleep %(sleep)ss
fi

echo completed $1
mv paused$1.log completed$1.log
"""


def set_defaults(dictionary, **kwargs):

    for item, value in kwargs.items():
        dictionary.setdefault(item, value)


def strfdelta(tdelta, fmt):
    """
    From https://stackoverflow.com/a/8907269
    """

    d = {}
    d["hours"], rem = divmod(tdelta.seconds, 3600)
    d["hours"] += tdelta.days * 24
    d["minutes"], d["seconds"] = divmod(rem, 60)
    return fmt % d


def infer_verification_name():

    for stack in inspect.stack():
        if stack[3].startswith("verify_"):
            return stack[3]

    raise RuntimeError("Cannot infer verification name:\n %s" %
                       "\n".join(str(t) for t in traceback.format_stack())) 


def build_argv(coresPerCommand, gpusPerCommand, walltime, coresPerNode,
               gpusPerNode, batchName=None, commandsFile=None,
               doNotLaunch=False, autoresume=False, pool=None,
               sbatchFlags=None):

    if batchName is None:
        batchName = infer_verification_name()

    argv = """
-vv
--queueName dummy
--batchName %(batchName)s --walltime %(walltime)s
--coresPerCommand %(coresPerCommand)s
--gpusPerCommand %(gpusPerCommand)s
--coresPerNode %(coresPerNode)s
--gpusPerNode %(gpusPerNode)s
    """ % dict(batchName=batchName,
               walltime=strfdelta(
                   datetime.timedelta(seconds=walltime),
                   "%(hours)02d:%(minutes)02d:%(seconds)02d"),
               coresPerCommand=coresPerCommand,
               gpusPerCommand=gpusPerCommand,
               coresPerNode=coresPerNode,
               gpusPerNode=gpusPerNode)

    # File containing commands to launch. Each command must
    # be on a seperate line. (Replaces commandAndOptions)
    if commandsFile:
        argv += " --commandsFile " + commandsFile

    # Generate all the files without launching the job.
    if doNotLaunch:
        argv += " --doNotLaunch"

    # Requeue the job when the running time hits the maximum
    # walltime allowed on the cluster. Assumes that commands
    # are resumable.
    if autoresume:
        argv += " --autoresume"     

    # Number of workers that will be consuming commands.
    # Default: Nb commands
    if pool:
        argv += " --pool " + pool

    # ADVANCED USAGE: Allow to pass a space seperated list of SBATCH flags.
    # Ex:--sbatchFlags="--qos=high --ofile.out"
    if sbatchFlags:
        argv += " --sbatchFlags=" + sbatchFlags

    return argv.replace("\n", " ")


def get_squeue():
    command = ("squeue -u %(username)s" %
               dict(username=getpass.getuser()))
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    stdout, stderr = process.communicate()
    return stdout


def try_to_remove_file(filename_template, expected_number):
    file_names = glob.glob(filename_template)
    try:
        i = 0
        for file_name in file_names:
            i += 1
            os.remove(file_name)
    except OSError as e:
        print(str(e))

    if i != expected_number:
        print("Error: Expected %d files, found %d" % (expected_number, i))
    else:
        print("OK: All %d files %s were found:\n%s" % (
            expected_number, filename_template,
            "\n".join(sorted(file_names))))


def minimum_requirement(attribute_name, minimum_value):

    def decorator(method):

        @functools.wraps(method)
        def call(self, *args, **kwargs):

            # Method was called from another verification
            try:
                verification_name = infer_verification_name()
            # Method was called directly 
            except RuntimeError:
                verification_name = method.__name__

            if not hasattr(self, attribute_name):
                raise ValueError("Invalid requirement, object %s does not "
                                 "have attribute %s" %
                                 (self.__class__.__name__, attribute_name))

            if getattr(self, attribute_name) >= minimum_value:
                return method(self, *args, **kwargs)
            else:
                print(("%s does not have enough %s: %d."
                       "Skipping %s." %
                       (self.__class__.__name__, attribute_name, minimum_value,
                        verification_name)))
                return None

        return call

    return decorator


class VerifySlurmCluster(object):

    WALLTIME = 60
    CORES_PER_NODE = 8
    GPUS_PER_NODE = 0

    def __init__(self, debug=False, no_fork=False):
        self.debug = debug
        self.no_fork = no_fork

    def get_verification_methods(self, filtered_by=None):
         methods = inspect.getmembers(self, predicate=inspect.ismethod)

         def filtering(item):
             key = item[0]

             if not key.startswith("verify_"):
                 return False
             elif filtered_by is not None and key not in filtered_by:
                 return False

             return True

         return dict(filter(filtering, methods))

    def run_verifications(self, filtered_by=None):
        if filtered_by is not None and len(filtered_by) == 0:
            filtered_by = None

        verification_methods = self.get_verification_methods(filtered_by)
        processes = []
        for verification_name, verification_fct in \
                    verification_methods.items():
            print("========%s" % ("=" * len(verification_name)))
            print("Running %s" % verification_name)
            print("========%s\n\n" % ("=" * len(verification_name)))

            if self.debug or self.no_fork:
                verification_fct()
            else:
                # fork the process in a new dir and new stdout, stderr
                verification_dir = os.path.join(
                    os.getcwd(), self.__class__.__name__, verification_name)

                if not os.path.isdir(verification_dir):
                    os.makedirs(verification_dir)

                stdout = open(os.path.join(verification_dir,
                                           "validation.out"), 'w')
                stderr = open(os.path.join(verification_dir,
                                           "validation.err"), 'w')

                popen = subprocess.Popen(
                    "/bin/bash",
                    shell=True, 
                    stdin=subprocess.PIPE,
                    stdout=stdout,
                    stderr=stderr)

                popen.stdin.write("cd %s;" % verification_dir)

                script_path = os.path.join(
                    os.getcwd(), inspect.getfile(self.__class__))
                popen.stdin.write(
                    "python %s --no-fork %s;" % (
                        script_path, verification_name))
                print("python %s --no-fork %s;" % (
                    script_path, verification_name))

                processes.append(popen)

        for popen in processes:
            # popen.communicate()
            popen.terminate()

    def run_test(self, argv, command_string, command_arguments=""):
        FILE_NAME = "test.sh"

        with open("test.sh", "w") as text_file:
            text_file.write(command_string)

        command = ("smart-dispatch %s launch bash %s %s" %
                   (argv, FILE_NAME, command_arguments))
        print("running test with command: ")
        print(command)

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        stdout, stderr = process.communicate()

        print("\nstdout:")
        print(stdout.decode())

        print("\nstderr:")
        print(stderr.decode())
        return stdout.split("\n")[-2].strip()

    def validate(self, root_dir, argv, squeue_wait, nb_of_commands=1,
                 resume=False):

        print("\nValidating arguments:")
        print(argv)

        stdout = get_squeue()
        number_of_process = stdout.count("\n") - 1

        while number_of_process > 0:
            root = os.path.join(root_dir, "commands")
            for file_path in os.listdir(root):
                if file_path.endswith(".sh"):
                    print(file_path)
                    print(open(os.path.join(root, file_path), 'r').read())

            print(stdout)
            print("Waiting %d seconds" % squeue_wait)
            time.sleep(squeue_wait)
            stdout = get_squeue()
            number_of_process = stdout.count("\n") - 1
            print(stdout)
            print(number_of_process)

        try_to_remove_file("running*.log", expected_number=nb_of_commands)
        try_to_remove_file("resumed*.log",
                           expected_number=nb_of_commands * int(resume))
        try_to_remove_file("completed*.log", expected_number=nb_of_commands)

        root = os.path.join(root_dir, "logs")
        for file_path in reversed(sorted(os.listdir(root))):
            if file_path.endswith(".err") or file_path.endswith(".out"):
                print(file_path)
                print(open(os.path.join(root, file_path), 'r').read())
                if self.debug:
                    pdb.set_trace()

    def get_arguments(self, **kwargs):

        set_defaults(
            kwargs,
            coresPerCommand=1,
            gpusPerCommand=0,
            walltime=self.WALLTIME,
            coresPerNode=self.CORES_PER_NODE,
            gpusPerNode=self.GPUS_PER_NODE)

        return kwargs

    def base_verification(self, sleep_time=0, command_arguments="",
                          resume=False, squeue_wait=None, nb_of_commands=1,
                          **kwargs):

        if squeue_wait is None and self.debug:
            squeue_wait = sleep_time + 5
        elif squeue_wait is None:
            squeue_wait = self.WALLTIME * 2
        
        arguments = self.get_arguments(**kwargs)
        argv = build_argv(**arguments)

        root_dir = self.run_test(argv, command_string % dict(sleep=sleep_time),
                                 command_arguments=command_arguments)
        self.validate(root_dir, argv, squeue_wait, nb_of_commands,
                      resume=resume)

    def verify_simple_task(self, **kwargs):
        self.base_verification(**kwargs)

    def verify_simple_task_with_one_gpu(self, **kwargs):
        set_defaults(
            kwargs,
            gpusPerCommand=1,
            gpusPerNode=1)

        self.verify_simple_task(**kwargs)

    @minimum_requirement("GPUS_PER_NODE", 2)
    def verify_simple_task_with_many_gpus(self, **kwargs):

        for gpus_per_command in range(2, self.GPUS_PER_NODE + 1):
            arguments = kwargs.copy()
            arguments["gpusPerCommand"] = gpus_per_command

            self.verify_simple_task(**arguments)

    @minimum_requirement("CORES_PER_NODE", 2)
    def verify_many_task(self, **kwargs):
        set_defaults(
            kwargs,
            nb_of_commands=self.CORES_PER_NODE)

        command_arguments = (
            "[%s]" % " ".join(str(i) for i in range(kwargs["nb_of_commands"])))

        set_defaults(
            kwargs,
            command_arguments=command_arguments)

        self.verify_simple_task(**kwargs)

    @minimum_requirement("CORES_PER_NODE", 4)
    def verify_many_task_with_many_cores(self, **kwargs):
        for cores_per_command in range(2, self.CORES_PER_NODE):
            if cores_per_command // self.CORES_PER_NODE <= 1:
                break

            arguments = kwargs.copy()
            arguments["cores_per_command"] = cores_per_command
            arguments["nb_of_commands"] = (
                cores_per_command //
                self.CORES_PER_NODE)

            self.many_task(**arguments)

    @minimum_requirement("GPUS_PER_NODE", 2)
    def verify_many_task_with_one_gpu(self, **kwargs):
        set_defaults(
            kwargs,
            nb_of_commands=self.GPUS_PER_NODE,
            gpusPerCommand=1)

        self.verify_many_task(**kwargs)

    @minimum_requirement("GPUS_PER_NODE", 4)
    def verify_many_task_with_many_gpus(self, **kwargs):
        for gpus_per_command in range(2, self.GPUS_PER_NODE + 1):
            if gpus_per_command // self.GPUS_PER_NODE <= 1:
                break

            arguments = kwargs.copy()
            arguments["gpusPerCommand"] = gpus_per_command
            arguments["nb_of_commands"] = (
                gpus_per_command //
                self.GPUS_PER_NODE)

            self.verify_many_task_with_one_gpu(**arguments)

    def verify_simple_task_with_autoresume_unneeded(self, **kwargs):
        walltime = 2 * 60
        set_defaults(
            kwargs,
            walltime=walltime,
            resume=False,
            autoresume=True)

        self.verify_simple_task(**kwargs)

    def verify_simple_task_with_autoresume_needed(self, **kwargs):
        walltime = 2 * 60
        set_defaults(
            kwargs,
            sleep_time=walltime,
            walltime=walltime,
            resume=True,
            autoresume=True)

        self.verify_simple_task(**kwargs)

    def verify_many_task_with_autoresume_needed(self, **kwargs):
        walltime = 2 * 60
        set_defaults(
            kwargs,
            sleep_time=walltime,
            walltime=walltime,
            resume=True,
            autoresume=True)

        self.verify_many_task(**kwargs)

    # def verify_pool(self, **kwargs):
    #     pass
