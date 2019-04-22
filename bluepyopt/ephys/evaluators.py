"""Cell evaluator class"""

"""
Copyright (c) 2016, EPFL/Blue Brain Project

 This file is part of BluePyOpt <https://github.com/BlueBrain/BluePyOpt>

 This library is free software; you can redistribute it and/or modify it under
 the terms of the GNU Lesser General Public License version 3.0 as published
 by the Free Software Foundation.

 This library is distributed in the hope that it will be useful, but WITHOUT
 ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
 FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
 details.

 You should have received a copy of the GNU Lesser General Public License
 along with this library; if not, write to the Free Software Foundation, Inc.,
 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""


# pylint: disable=W0511

import logging
from multiprocessing import Process,Manager
import bluepyopt as bpopt
import bluepyopt.tools
import time
import numpy as np

logger = logging.getLogger(__name__)

class TimeoutException(Exception):   # Custom exception class
   pass

def timeout_handler(signum, frame):   # Custom signal handler
   raise TimeoutException

class CellEvaluator(bpopt.evaluators.Evaluator):

    """Simple cell class"""

    def __init__(
            self,
            cell_model=None,
            param_names=None,
            fitness_protocols=None,
            fitness_calculator=None,
            isolate_protocols=None,
            sim=None,
            use_params_for_seed=False,
            **kwargs):
        """Constructor

        Args:
            cell_model (ephys.models.CellModel): CellModel object to evaluate
            param_names (list of str): names of the parameters
                (parameters will be initialised in this order)
            fitness_protocols (dict of str -> ephys.protocols.Protocol):
                protocols used during the fitness evaluation
            fitness_calculator (ObjectivesCalculator):
                ObjectivesCalculator object used for the transformation of
                Responses into Objective objects
            isolate_protocols (bool): whether to use multiprocessing to
                isolate the simulations
                (disabling this could lead to unexpected behavior, and might
                hinder the reproducability of the simulations)
            sim (ephys.simulators.NrnSimulator): simulator to use for the cell
                evaluation
            use_params_for_seed (bool): use a hashed version of the parameter
                dictionary as a seed for the simulator
        """

        super(CellEvaluator, self).__init__(
            fitness_calculator.objectives,
            cell_model.params_by_names(param_names))

        if sim is None:
            raise ValueError("CellEvaluator: you have to provide a Simulator "
                             "object to the 'sim' argument of the "
                             "CellEvaluator constructor")
        self.sim = sim

        self.cell_model = cell_model
        self.param_names = param_names
        # Stimuli used for fitness calculation
        self.fitness_protocols = fitness_protocols
        # Fitness value calculator
        self.fitness_calculator = fitness_calculator

        self.isolate_protocols = isolate_protocols
        self.use_params_for_seed = use_params_for_seed

    def param_dict(self, param_array):
        """Convert param_array in param_dict"""
        param_dict = {}
        for param_name, param_value in \
                zip(self.param_names, param_array):
            param_dict[param_name] = param_value

        return param_dict

    def objective_dict(self, objective_array):
        """Convert objective_array in objective_dict"""
        objective_dict = {}
        objective_names = [objective.name
                           for objective in self.fitness_calculator.objectives]

        if len(objective_names) != len(objective_array):
            raise Exception(
                'CellEvaluator: list given to objective_dict() '
                'has wrong number of objectives')

        for objective_name, objective_value in \
                zip(objective_names, objective_array):
            objective_dict[objective_name] = objective_value

        return objective_dict

    def objective_list(self, objective_dict):
        """Convert objective_dict in objective_list"""
        objective_list = []
        objective_names = [objective.name
                           for objective in self.fitness_calculator.objectives]
        for objective_name in objective_names:
            objective_list.append(objective_dict[objective_name])

        return objective_list

    @staticmethod
    def seed_from_param_dict(param_dict):
        """Return a seed value based on a param_dict"""

        sorted_keys = sorted(param_dict.keys())

        string_ = ''
        for key in sorted_keys:
            string_ += '%s%s' % (key, str(param_dict[key]))

        return bluepyopt.tools.uint32_seed(string_)

    def run_protocol(
            self,
            protocol,
            param_values,
            isolate=None,
            cell_model=None,
            sim=None):
        """Run protocol"""

        sim = self.sim if sim is None else sim

        if self.use_params_for_seed:
            sim.random123_globalindex = self.seed_from_param_dict(param_values)

        return protocol.run(
            self.cell_model if cell_model is None else cell_model,
            param_values,
            sim=sim,
            isolate=isolate)

    def run_protocols(self, protocols, param_values):
        """Run a set of protocols"""

        responses = {}

        for protocol in protocols:
            responses.update(self.run_protocol(
                protocol,
                param_values=param_values,
                isolate=self.isolate_protocols))

        return responses

    def evaluate_with_dicts(self, param_dict=None,timeout_stat = None):
        """Run evaluation with dict as input and output"""

        if self.fitness_calculator is None:
            raise Exception(
                'CellEvaluator: need fitness_calculator to evaluate')

        logger.debug('Evaluating %s', self.cell_model.name)

        responses = self.run_protocols(
            self.fitness_protocols.values(),
            param_dict)

        return self.fitness_calculator.calculate_scores(responses),None

    def save_response_lists(self, param_list=None):
        """Run simulation with lists as input and outputs"""

        param_dict = self.param_dict(param_list)
        logger.debug('Evaluating %s', self.cell_model.name)

        responses = self.run_protocols(
            self.fitness_protocols.values(),
            param_dict)
        return [responses]

    def evaluate_from_responses(self, response_list = None):
        """Run evaluation with response dictionary as input"""

        response_dict = response_list[0]
        return self.fitness_calculator.calculate_scores(response_dict)



    def evaluate_with_lists(self, param_list=None,timeout_stat=None):
        """Run evaluation with lists as input and outputs"""

        param_dict = self.param_dict(param_list)
        obj_dict,sim_dur = self.evaluate_with_dicts(param_dict=param_dict,
                                            timeout_stat= timeout_stat)

        return self.objective_list(obj_dict),sim_dur

    def evaluate(self, param_list=None):
        """Run evaluation with lists as input and outputs"""

        return self.evaluate_with_lists(param_list)

    def __str__(self):

        content = 'cell evaluator:\n'

        content += '  cell model:\n'
        if self.cell_model is not None:
            content += '    %s\n' % str(self.cell_model)

        content += '  fitness protocols:\n'
        if self.fitness_protocols is not None:
            for fitness_protocol in self.fitness_protocols.values():
                content += '    %s\n' % str(fitness_protocol)

        content += '  fitness calculator:\n'
        if self.fitness_calculator is not None:
            content += '    %s\n' % str(self.fitness_calculator)

        return content


class CellEvaluatorTimed(CellEvaluator):

    """Timed evaluation cell class"""
    def __init__(self, **kwargs):
        super(CellEvaluatorTimed, self).__init__(**kwargs)
        self.timeout_thresh = kwargs.get('timeout',900)
        self.timeout_thresh_min = kwargs.get('timeout_min',60)
#        self.eval_range = kwargs.get('eval_range',2)
#        self.cutoff_mode = kwargs.get('cutoff_mode')
        
    
    def evaluate_with_dicts(self, param_dict=None,timeout_stat = None):
        """Run evaluation with dict as input and output"""
        
        if timeout_stat:
            print('time out stats {} seconds'.format(timeout_stat))
        if self.fitness_calculator is None:
            raise Exception(
                'CellEvaluator: need fitness_calculator to evaluate')

        logger.debug('Evaluating %s', self.cell_model.name)
        
        timeout = min(self.timeout_thresh,timeout_stat)
        timeout = max(self.timeout_thresh_min,timeout_stat)
        
        def run_func(return_dict):
            results = self.run_protocols(
                self.fitness_protocols.values(),
                param_dict)

            return_dict['resp'] = results



        def timed_sim(func, args, kwargs, timeout):
            """Runs a function with time limit

            :param func: The function to run
            :param args: The functions args, given as tuple
            :param kwargs: The functions keywords, given as dict
            :param timeout: The time limit in seconds

            """
            manager = Manager()
            return_dict = manager.dict()
            p = Process(target=func, args=(return_dict,),
                                    kwargs=kwargs)
            p.start()
            p.join(timeout)
            if p.is_alive():
                p.terminate()
                print('Individual missed cut-off @%s seconds'\
                      %timeout)
            del p
            return return_dict
        
        start_time = time.time()
        resp_dict= timed_sim(run_func,(),{},timeout)
        end_time = time.time()
        sim_dur = end_time - start_time
        print('Simulation duration = {t} seconds for the individual'\
              .format(t=sim_dur))
        return self.fitness_calculator.calculate_scores(resp_dict.get('resp',{})),sim_dur


#    def evaluate_with_dicts(self, param_dict=None):
#        """Run evaluation with dict as input and output"""
#
#        logger.debug('Evaluating %s', self.cell_model.name)
#
#        responses = {}
#
#        for protocol in self.fitness_protocols.values():
#            proto_stat_thresh = self.timeout_thresh
#            if self.cutoff_mode:
#                try:
#                    proto_stat_pattern = glob.glob(os.path.join(self.eval_stat_dir,\
#                                                            '%s*'%protocol.name))
#                    proto_stat = [int(pickle.load(open(file_,'rb')))+1 \
#                                  for file_ in proto_stat_pattern]
#    
#                    proto_stat_thresh = max(set(proto_stat), key=proto_stat.count) \
#                                if len(proto_stat)>4e1 else self.timeout_thresh # Mode
#                    print('Mode for sim duration = {} seconds'.format(proto_stat_thresh))
#                except:
#                    pass
#
#            timeout_var = min(proto_stat_thresh,self.timeout_thresh)
#
#            def run_func(return_dict):
#                results = self.run_protocol(
#                    protocol,
#                    param_values=param_dict,
#                    isolate=self.isolate_protocols)
#
#                return_dict['resp'] = results
#
#
#
#            def timed_sim(func, args, kwargs, timeout):
#                """Runs a function with time limit
#
#                :param func: The function to run
#                :param args: The functions args, given as tuple
#                :param kwargs: The functions keywords, given as dict
#                :param timeout: The time limit in seconds
#
#                """
#                manager = Manager()
#                return_dict = manager.dict()
#                p = Process(target=func, args=(return_dict,),
#                                        kwargs=kwargs)
#                p.start()
#                p.join(timeout)
#                if p.is_alive():
#                    p.terminate()
#                    print('Simulation missed cut-off for protocol %s @%s seconds'\
#                          %(protocol.name,timeout))
#                del p
#                return return_dict
#
#            start_time = time.time()
#            resp_dict= timed_sim(run_func,(),{},timeout_var)
#            end_time = time.time()
#            sim_dur = end_time - start_time
#            print('Simulation duration = {t} seconds for protocol {proto}'\
#                  .format(t=sim_dur,proto=protocol.name))
#
#            if bool(resp_dict):
#                responses.update(resp_dict['resp'])
#                
#                if self.cutoff_mode:
#                    rnd_str = ''.join([random.choice(string.ascii_letters + string.digits) \
#                                       for n in range(self.eval_range)])
#                    stat_filename = '%s_%s.pkl'%(protocol.name,rnd_str)
#                    stat_filepath = os.path.join(self.eval_stat_dir,stat_filename)
#                    with open(stat_filepath, "wb") as stat:
#                        pickle.dump(sim_dur,stat)
#
#        return self.fitness_calculator.calculate_scores(responses)
#
