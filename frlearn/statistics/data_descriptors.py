"""Statistical data descriptors"""
from __future__ import annotations

import numpy as np
from scipy import linalg
from scipy.stats import chi2

from frlearn.statistics.feature_preprocessors import Standardiser
from ..base import DataDescriptor
from ..utils.np_utils import shifted_reciprocal


class CD(DataDescriptor):
    """
    Implementation of the Centre Distance (CD) data descriptor.
    Calculates a score based on the distance to a central point of the target data.

    This is implemented as simply the norm of each element (the distance to the origin),
    with the expectation that the given preprocessor normalises the data in such a way that
    a suitable central value of the data is located at the origin,
    and that all features have the same scale.

    By default (standardisation) this is centroid distance.

    Parameters
    ----------
    ord: float = 2
        Order of the norm to use. Can also be `-np.inf` or `np.inf`.

    threshold_perc : int or None, default=80
        Threshold percentile for normal instances. Should be in (0, 100] or None.
        All distances below the distance value in the target set corresponding to this percentile
        result in a final score above 0.5. If None, 1 is used as the threshold instead.

    preprocessors : iterable = (Standardiser(), )
        Preprocessors to apply. The default standardiser places the centroid of the data at the origin,
        and ensures that all features have the same standard deviation.
    """

    def __init__(
            self,
            ord: float = 2,
            threshold_perc: int | None = 80,
            preprocessors=(Standardiser(), )
    ):
        super().__init__(preprocessors=preprocessors)
        self.ord = ord
        self.threshold_perc = threshold_perc

    def _construct(self, X) -> Model:
        model: CD.Model = super()._construct(X)
        model.ord = self.ord
        if self.threshold_perc:
            distances = model._distances(X)
            model.threshold = np.percentile(distances, self.threshold_perc)
        else:
            model.threshold = 1
        return model

    class Model(DataDescriptor.Model):

        ord: float
        threshold: float

        def _query(self, X):
            distances = self._distances(X)
            return shifted_reciprocal(distances, self.threshold)

        def _distances(self, X):
            return np.linalg.norm(X, ord=self.ord, axis=1)


class MD(DataDescriptor):
    """
    Implementation of the Mahalanobis Distance (MD) data descriptor [1]_.
    Mahalanobis distance is the multivariate generalisation of distance to the mean in terms of σ,
    in a Gaussian distribution. This data descriptor simply assumes that the target class is normally distributed,
    and uses the pseudo-inverse of its covariance matrix to transform a vector with deviations from the mean
    in each dimension into a single distance value.
    Squared Mahalanobis distance is χ²-distributed, the corresponding p-value is the confidence score.

    Parameters
    ----------
    preprocessors : iterable = ()
        Preprocessors to apply.

    References
    ----------

    .. [1] `Mahalanobis PC (1936).
       On the generalized distance in statistics.
       Proceedings of the National Institute of Sciences of India, vol 2, no 1, pp 49–55.
       <http://insa.nic.in/writereaddata/UpLoadedFiles/PINSA/Vol02_1936_1_Art05.pdf>`_
    """

    def __init__(self, preprocessors=()):
        super().__init__(preprocessors=preprocessors)

    def _construct(self, X) -> Model:
        model: MD.Model = super()._construct(X)
        model.mean = X.mean(axis=0)
        model.covar_inv = linalg.pinvh(np.cov(X.T, bias=True))
        return model

    class Model(DataDescriptor.Model):

        mean: np.array
        covar_inv: np.array

        def _query(self, X):
            d = X - self.mean
            D2 = (d[..., None, :] @ self.covar_inv @ d[..., None]).squeeze(axis=(-2, -1))
            return 1 - chi2.cdf(D2, df=self.m)
