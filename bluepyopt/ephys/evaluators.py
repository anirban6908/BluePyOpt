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

#from IPython.config import Application

#logger = Application.instance().log
logger = logging.getLogger(__name__)



import bluepyopt as bpopt
import bluepyopt.tools

import time


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
            use_params_for_seed=False):
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

        string = ''
        for key in sorted_keys:
            string += '%s%s' % (key, str(param_dict[key]))

        return bluepyopt.tools.uint32_seed(string)

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

    def evaluate_with_dicts(self, param_dict=None):
        """Run evaluation with dict as input and output"""

        if self.fitness_calculator is None:
            raise Exception(
                'CellEvaluator: need fitness_calculator to evaluate')

        logger.debug('Evaluating %s', self.cell_model.name)

        responses = self.run_protocols(
            self.fitness_protocols.values(),
            param_dict)

        return self.fitness_calculator.calculate_scores(responses)
    
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

    
    
    def evaluate_with_lists(self, param_list=None):
        """Run evaluation with lists as input and outputs"""

        param_dict = self.param_dict(param_list)

        obj_dict = self.evaluate_with_dicts(param_dict=param_dict)

        return self.objective_list(obj_dict)

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

    def evaluate_with_dicts(self, param_dict=None):
        """Run evaluation with dict as input and output"""

        logger.debug('Evaluating %s', self.cell_model.name)

        responses = {}
        
        for protocol in self.fitness_protocols.values():

            start_time = time.time()
            results = self.run_protocol(
                protocol,
                param_values=param_dict,
                isolate=self.isolate_protocols)
            responses.update(results)
                
            end_time = time.time()
            sim_dur = end_time - start_time
            if sim_dur > 300:
                logger.debug('Simulation cut-off')
                break
        return self.fitness_calculator.calculate_scores(responses)

