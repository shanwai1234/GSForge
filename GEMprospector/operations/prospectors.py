"""
Prospector operations return either boolean support arrays or arrays
of selected genes. While these may include some values / ranks, prospector
operations differ from analyzer operations, in that they are not expected
to return results for every gene.
"""

import enum
import json
from textwrap import dedent

import numpy as np
import param
import xarray as xr
from boruta import boruta_py

from ..models import OperationInterface
from ..utils import kwargs_overlap


__all__ = [
    "create_random_lineament",
    "parse_boruta_model",
    "boruta_prospector",
]


class create_random_lineament(OperationInterface):
    """
    Creates a random lineament of size `k`.

    Picks from the gene index defined by the `Interface` options.
    """
    k = param.Integer(default=100)

    def process(self):
        random_genes = np.random.choice(self.gene_index, self.k)
        return random_genes, {"random_size": self.k}


class _model_parsers(enum.Enum):
    boruta = {
        "support": lambda d, m: ([d], np.array(getattr(m, "support_"), dtype=bool)),
        "support_weak": lambda d, m: ([d], np.array(getattr(m, "support_weak_"), dtype=bool)),
        "ranking": lambda d, m: ([d], np.array(getattr(m, "ranking_"))),
    }


def _parse_model(model, model_type, dim) -> dict:
    """Parse a model into a dictionary appropriate for constructing an `Xarray.Dataset`.

    :param model: The model object to be parsed.

    :param model_type: The key to the Enum `_model_parsers`.

    :param dim:

    :return:
    """
    parsing_dict = _model_parsers[model_type].value
    return {key: func(dim, model) for key, func in parsing_dict.items()}


def parse_boruta_model(boruta_model, gene_coords, attrs=None, dim="Gene") -> xr.Dataset:
    """Convert a boruta model into an `xarray.Dataset` object.

    :param boruta_model: A boruta_py model.

    :param attrs: A dictionary to be assigned to the output dataset attrs.

    :param gene_coords: An array (index) of the genes passed to the boruta_model.

    :param dim: The name of the coordinate dimension.

    :return: An `xarray.Dataset` object.
    """
    model_data = _parse_model(boruta_model, "boruta", dim=dim)
    return xr.Dataset(model_data, coords={dim: gene_coords}, attrs=attrs)


# TODO: Consider a direct to GeneSet object option.
class boruta_prospector(OperationInterface):
    """Runs a single instance of BorutaPy feature selection.

    This is just a simple wrapper for a boruta model that produces an
    `xarray.Dataset` object suitable for use in the creation of a
    `GEMprospector.GeneSet` object."""

    estimator = param.Parameter(doc=dedent("""\
    A supervised learning estimator, with a 'fit' method that returns the
    `feature_importances_` attribute. Important features must correspond to
    high absolute values in the `feature_importances_`."""))

    n_estimators = param.Parameter(default=1000, doc=dedent("""\
    If int sets the number of estimators in the chosen ensemble method.
    If 'auto' this is determined automatically based on the size of the
    dataset. The other parameters of the used estimators need to be set
    with initialisation."""))

    perc = param.Integer(default=100, doc=dedent("""\
    Instead of the max we use the percentile defined by the user, to pick
    our threshold for comparison between shadow and real features. The max
    tend to be too stringent. This provides a finer control over this. The
    lower perc is the more false positives will be picked as relevant but
    also the less relevant features will be left out. The usual trade-off.
    The default is essentially the vanilla Boruta corresponding to the max.
    """))

    alpha = param.Number(default=0.05, doc=dedent("""\
    Level at which the corrected p-values will get rejected in both
    correction steps."""))

    two_step = param.Boolean(default=True, doc=dedent("""\
    If you want to use the original implementation of Boruta with Bonferroni
    correction only set this to False."""))

    max_iter = param.Integer(default=100, doc=dedent("""\
    The number of maximum iterations to perform."""))

    random_state = param.Parameter(default=None, doc=dedent("""\
    If int, random_state is the seed used by the random number generator;
    If RandomState instance, random_state is the random number generator;
    If None, the random number generator is the RandomState instance used
    by `np.random`."""))

    verbose = param.Integer(default=0, doc=dedent("""\
    Controls verbosity of output:
    - 0: no output
    - 1: displays iteration number
    - 2: which features have been selected already"""))

    def process(self):
        x_data, y_data = self.x_count_data, self.y_annotation_data
        boruta_kwargs = kwargs_overlap(self, boruta_py.BorutaPy)
        boruta_model = boruta_py.BorutaPy(**boruta_kwargs)
        boruta_model.fit(x_data, y_data)

        # Convert attribute dictionaries to .json format.
        # We can't store nested dictionaries in the attrs.
        boruta_json_attrs = json.dumps(boruta_kwargs, default=lambda o: '<not serializable>')
        ranking_model_json_attrs =  json.dumps(self.estimator.get_params(), default=lambda o: '<not serializable>')

        attrs = {'boruta_model': boruta_json_attrs,
                 'ranking_model': ranking_model_json_attrs,
                 "selected_count_variable": self.selected_count_variable,
                 "selected_annotation_variables": self.selected_annotation_variables}

        return parse_boruta_model(boruta_model, attrs=attrs, gene_coords=self.get_gene_index(),
                                  dim=self.gem.gene_index_name)


# class boruta_one_vs_rest_prospector(boruta_prospector):
#     def process(self):
#         pass

