import sys

from verify_slurm_cluster import VerifySlurmCluster, set_defaults


class VerifyCedarCluster(VerifySlurmCluster):

    WALLTIME = 60
    CORES_PER_NODE = 24
    GPUS_PER_NODE = 4

    def get_arguments(self, **kwargs):

        set_defaults(
            kwargs,
            coresPerCommand=1,
            gpusPerCommand=0,
            walltime=self.WALLTIME,
            coresPerNode=self.CORES_PER_NODE,
            gpusPerNode=self.GPUS_PER_NODE)

        return kwargs


if __name__ == "__main__":
    verifications = filter(lambda o: not o.startswith("--"), sys.argv[1:])
    VerifyCedarCluster(debug="--debug" in sys.argv[1:],
                       no_fork="--no-fork" in sys.argv[1:]).run_verifications(
        filtered_by=verifications)
