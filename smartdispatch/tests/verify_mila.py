import sys

from verify_slurm_cluster import VerifySlurmCluster, set_defaults


class VerifyMILACluster(VerifySlurmCluster):

    WALLTIME = 60
    CORES_PER_NODE = 8
    GPUS_PER_NODE = 2

    def get_arguments(self, **kwargs):

        set_defaults(
            kwargs,
            coresPerCommand=1,
            gpusPerCommand=0,
            walltime=self.WALLTIME,
            coresPerNode=self.CORES_PER_NODE,
            gpusPerNode=self.GPUS_PER_NODE)

        return kwargs

    def verify_simple_task_with_constraints(self, **kwargs):

        set_defaults(
            kwargs,
            gpusPerCommand=1,
            sbatchFlags='"-C\"gpu12gb\""')

        self.base_verification(**kwargs)


if __name__ == "__main__":
    verifications = [o for o in sys.argv[1:] if not o.startswith("--")]
    VerifyMILACluster(debug="--debug" in sys.argv[1:],
                      no_fork="--no-fork" in sys.argv[1:]).run_verifications(
        filtered_by=verifications)
