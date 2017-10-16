# -*- coding: utf-8 -*-
import random

import unittest
try:
    from mock import patch
except ImportError:
    from unittest.mock import patch

from nose.tools import assert_equal, assert_true

from numpy.testing import assert_array_equal
import subprocess

from smartdispatch import utils


class TestWalltimeToSeconds(unittest.TestCase):
    def setUp(self):
        self.format = dict(
            days=random.randint(0, 10),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59))

    def _compute_seconds(self, days=0, hours=0, minutes=0, seconds=0):
        return ((((days * 24) + hours) * 60) + minutes * 60) + seconds

    def test_ddhhmmss(self):
        seconds = utils.walltime_to_seconds(
            "{days}:{hours}:{minutes}:{seconds}".format(**self.format))
        self.assertEqual(seconds, self._compute_seconds(**self.format))

    def test_hhmmss(self):
        truncated_format = self.format.copy()
        truncated_format.pop("days")

        seconds = utils.walltime_to_seconds(
            "{hours}:{minutes}:{seconds}".format(**truncated_format))
        self.assertEqual(seconds, self._compute_seconds(**truncated_format))

    def test_mmss(self):
        truncated_format = self.format.copy()
        truncated_format.pop("days")
        truncated_format.pop("hours")

        seconds = utils.walltime_to_seconds(
            "{minutes}:{seconds}".format(**truncated_format))
        self.assertEqual(seconds, self._compute_seconds(**truncated_format))

    def test_ss(self):
        truncated_format = self.format.copy()
        truncated_format.pop("days")
        truncated_format.pop("hours")
        truncated_format.pop("minutes")

        seconds = utils.walltime_to_seconds(
            "{seconds}".format(**truncated_format))
        self.assertEqual(seconds, self._compute_seconds(**truncated_format))

    def test_too_much_columns(self):
        with self.assertRaises(ValueError):
            seconds = utils.walltime_to_seconds(
                "1:{days}:{hours}:{minutes}:{seconds}".format(**self.format))

    def test_with_text(self):
        with self.assertRaises(ValueError):
            seconds = utils.walltime_to_seconds(
                "{days}hoho:{hours}:{minutes}:{seconds}".format(**self.format))


class PrintBoxedTests(unittest.TestCase):

    def setUp(self):
        self.empty = ''
        self.text = "This is weird test for a visual thing.\nWell maybe it's fine to test it's working."

    def test_print_boxed(self):
        utils.print_boxed(self.text)

    def test_print_boxed_empty(self):
        utils.print_boxed(self.empty)


def test_chunks():
    sequence = range(10)

    for n in range(1, 11):
        expected = []
        for start, end in zip(range(0, len(sequence), n), range(n, len(sequence) + n, n)):
            expected.append(sequence[start:end])

        assert_array_equal(list(utils.chunks(sequence, n)), expected, "n:{0}".format(n))


def test_generate_uid_from_string():
    assert_equal(utils.generate_uid_from_string("same text"), utils.generate_uid_from_string("same text"))
    assert_true(utils.generate_uid_from_string("same text") != utils.generate_uid_from_string("sametext"))

def test_jobname_generator():
    assert_equal(len(utils.jobname_generator("a-string-which-has-a-longer-length-nnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn-than-64", 8798777)), 64)
    assert_equal(len(utils.jobname_generator("abcde",3)), 7)
    assert_equal(len(utils.jobname_generator("",21)), 3)

def test_slugify():
    testing_arguments = [("command", "command"),
                         ("/path/to/arg2/", "pathtoarg2"),
                         ("!\"/$%?&*()[]~{<>'.#|\\", ""),
                         ("éèàëöüùò±@£¢¤¬¦²³¼½¾", "eeaeouuo23141234"),  # ¼ => 1/4 => 14
                         ("arg with space", "arg_with_space")]

    for arg, expected in testing_arguments:
        assert_equal(utils.slugify(arg), expected)


command_output = """\
Server             Max   Tot   Que   Run   Hld   Wat   Trn   Ext   Com Status
----------------   ---   ---   ---   ---   ---   ---   ---   ---   --- ----------
gpu-srv1.{}      0  1674   524   121    47     0     0    22   960 Idle
"""

slurm_command = """\
   Cluster     ControlHost  ControlPort   RPC     Share GrpJobs       GrpTRES GrpSubmit MaxJobs       MaxTRES MaxSubmit     MaxWall                  QOS   Def QOS
---------- --------------- ------------ ----- --------- ------- ------------- --------- ------- ------------- --------- ----------- -------------------- ---------
      {}  132.204.24.224         6817  7680         1                                                                                           normal
"""


class ClusterIdentificationTest(unittest.TestCase):
    server_names = ["hades", "m", "guil", "helios", "hades"]
    clusters = ["hades", "mammouth", "guillimin", "helios"]
    command_output = command_output

    def __init__(self, *args, **kwargs):
        super(ClusterIdentificationTest, self).__init__(*args, **kwargs)
        self.detect_cluster = utils.detect_cluster

    def test_detect_cluster(self):

        with patch('smartdispatch.utils.Popen') as MockPopen:
            mock_process = MockPopen.return_value
            for name, cluster in zip(self.server_names, self.clusters):
                mock_process.communicate.return_value = (
                   self.command_output.format(name), "")
                self.assertEquals(self.detect_cluster(), cluster)


class SlurmClusterIdentificationTest(ClusterIdentificationTest):
    server_names = clusters = ["graham", "cedar", "mila"]
    command_output = slurm_command

    def __init__(self, *args, **kwargs):
        super(SlurmClusterIdentificationTest, self).__init__(*args, **kwargs)
        self.detect_cluster = utils.get_slurm_cluster_name
