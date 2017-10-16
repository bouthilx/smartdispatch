import sys

from verify_slurm_cluster import VerifySlurmCluster, set_defaults


class VerifyGrahamCluster(VerifySlurmCluster):

    WALLTIME = 60
    CORES_PER_NODE = 32
    GPUS_PER_NODE = 2

    def get_arguments(self, **kwargs):

        set_defaults(
            kwargs,
            coresPerCommand=1,
            gpusPerCommand=0,
            walltime=self.WALLTIME,
            coresPerNode=self.CORES_PER_NODE,
            gpusPerNode=self.GPUS_PER_NODE,
            sbatchFlags="--account=rpp-bengioy")

        return kwargs


if __name__ == "__main__":
    verifications = filter(lambda o: not o.startswith("--"), sys.argv[1:])
    VerifyGrahamCluster(debug="--debug" in sys.argv[1:],
                        no_fork="--no-fork" in sys.argv[1:]).run_verifications(
        filtered_by=verifications)
