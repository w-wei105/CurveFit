import numpy as np
from curvefit.utils.data import data_translator
from curvefit.core.data import Data
from curvefit.uncertainty.residual_model import _ResidualModel


# TODO: add tests
class Draws:
    """
        {begin_markdown _Draws}

        {spell_markdown subclassed covs}

        # `curvefit.uncertainty.draws.Draws`
        ## A class for generating draws: predictions plus random residuals according to provided ResidualModel

        This class simulates possible trajectories by adjusting out-of-sample part of the prediction
        with expected residuals from ResidualModel. The user-controlled parameters are passed via init; the
        parameters which need to be consistent to other parts of the pipeline (like `model`, `solver`,
         `evaluation_space`, etc) are passed via create_draws(...).

        ## Arguments
        - `num_draws (int)`: the number of draws to take
        - `prediction_times (np.array)`: which times to produce final predictions (draws) at
        - `exp_smoothing (float)`: amount of exponential smoothing --> higher value means more weight
                given to the more recent models
        - `max_last` (optional int) number of models from previous observations to use since the maximum time

        ## Methods
        ### `create_draws`
            Fills in the `draws` dictionary by generating `num_groups` sample trajectories per location
            - `data (curvefit.core.data.Data)`: data
            - `model_prototype (curvefit.models.base.Model)`: a model object
            - `solver_prototype (curvefit.solvers.solver.Solver)`: a solver used to fit the model
            - `residual_model (curvefit.uncertainty.residual_model._ResidualModel)' a residual model object, should be
                 fitted before being passed here.
            - `evaluation_space (callable)`: which space to generate draws in. It should be the same as used
                in `PredictiveValidity` instance which generated the residual matrix passed to the `residual_model`
            - `theta (float)`: between 0 and 1, how much scaling of the residuals to do relative to the prediction mean

        ## `get_draws`
            Returns generated draws
            - `group (str)`: Group for which the draws are requested. Defaults to None, in which case returns
                a dictionary of all draws indexed by groups.

        ## Usage
        In `ModelRunner.run()`:
        ```python
            draws = self.draws.create_draws(
                data=self.data,
                model_prototype=self.model,
                solver_prototype=self.solver,
                residual_model=self.residual_model,
                evaluation_space = self.predictive_validity.evaluation_space,
                theta=self.predictive_validity.theta
            ).get_draws()
            '''
        {end_markdown _ResidualModel}
        """

    def __init__(self, num_draws, prediction_times, exp_smoothing=None, max_last=None):

        self.num_draws = num_draws
        self.prediction_times = prediction_times
        self.exp_smoothing = exp_smoothing
        self.max_last = max_last
        self._draws = None

        assert type(self.num_draws) == int
        assert self.num_draws > 0

        assert type(self.prediction_times) == np.ndarray

        if self.exp_smoothing is not None:
            assert type(self.exp_smoothing) == float
            if self.max_last is None:
                raise RuntimeError("Need to pass in how many of the last models to use.")
            else:
                assert type(self.max_last) == int
                assert self.max_last > 0
        else:
            if self.max_last is not None:
                raise RuntimeError("Need to pass in exponential smoothing parameter.")

    # TODO: Implement exponential smoothing (do we need it?)
    def create_draws(self,
                     data: Data,
                     model_prototype,
                     solver_prototype,
                     residual_model: _ResidualModel,
                     evaluation_space,
                     theta: float):

        self._draws = {group: [] for group in data.groups}
        for group in data.groups:

            # Initializing model and doing the "best fit"
            model = model_prototype.clone()
            solver = solver_prototype.clone()
            solver.set_model_instance(model)
            current_group_data = data._get_df(group=group, copy=False)
            solver.fit(current_group_data)

            # getting predictions for draws times
            predictions = solver.predict(
                t=self.prediction_times,
                predict_fun=evaluation_space
            )

            max_t = int(np.round(current_group_data[data.col_t].max()))
            num_obs = int(sum(~current_group_data[data.col_obs].isnull()))

            add_noise = self.prediction_times > max_t
            no_noise = self.prediction_times <= max_t

            forecast_out_times = self.prediction_times[add_noise] - max_t
            error = residual_model.simulate_residuals(
                num_simulations=self.num_draws,
                covariate_specs={'num_data': num_obs, 'far_out': forecast_out_times}
            )
            no_error = np.zeros(shape=(self.num_draws, sum(no_noise)))
            all_error = np.hstack([no_error, error])

            noisy_forecast = predictions - (predictions ** theta) * all_error

            noisy_forecast = data_translator(
                data=noisy_forecast, input_space=evaluation_space, output_space=evaluation_space
            )
            self._draws[group].append(noisy_forecast)

        return self

    def get_draws(self, group=None):
        if self._draws is None:
            raise RuntimeError("Draws are not created yet: call create_draws(..) first.")

        if group is not None:
            return self._draws[group]
        else:
            return self._draws
