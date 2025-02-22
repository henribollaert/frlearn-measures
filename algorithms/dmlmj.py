"""
Distance Metric Learning through the Maximization of the Jeffrey divergence (DMLMJ)

Adapted from https://github.com/jlsuarezdiaz/pyDML:
@author: jlsuarezdiaz
"""

from __future__ import print_function, absolute_import
import numpy as np
from six.moves import xrange
from sklearn.metrics import pairwise_distances
from sklearn.utils.validation import check_X_y

from scipy.linalg import eigh

from .dml_algorithm import DML_Algorithm, KernelDML_Algorithm
from .dml_utils import pairwise_sq_distances_from_dot


class DMLMJ(DML_Algorithm):
    """
    Distance Metric Learning through the Maximization of the Jeffrey divergence (DMLMJ).

    A DML Algorithm that obtains a transformer that maximizes the Jeffrey divergence between
    the distribution of differences of same-class neighbors and the distribution of differences between
    different-class neighbors.

    Parameters
    ----------
    num_dims : int, default=None
        Dimension desired for the transformed data.

    n_neighbors : int, default=3
        Number of neighbors to consider in the computation of the difference spaces.

    alpha : float, default=0.001
        Regularization parameter for inverse matrix computation.

    reg_tol : float, default=1e-10
        Tolerance threshold for applying regularization. The tolerance is compared with the matrix determinant.

    References
    ----------
        Bac Nguyen, Carlos Morell and Bernard De Baets. “Supervised distance metric learning through
        maximization of the Jeffrey divergence”. In: Pattern Recognition 64 (2017), pages 215-225.
    """

    def __init__(self,
                 num_dims=None,
                 n_neighbors=3,
                 alpha=0.001,
                 reg_tol=1e-10):
        self.num_dims = num_dims
        self.n_neighbors = n_neighbors
        self.alpha = alpha
        self.reg_tol = reg_tol

        # Metadata
        self.acum_eig_ = None
        self.nd_ = None

    def transformer(self):
        """
        Obtains the learned projection.

        Returns
        -------
        L : (d'xd) matrix, where d' is the desired output dimension and d is the number of features.
        """
        return self.L_

    def metadata(self):
        """
        Obtains algorithm metadata.

        Returns
        -------
        meta : A dictionary with the following metadata:
            acum_eig : eigenvalue rate accumulated in the learned output respect to the total dimension.

            num_dims : dimension of the reduced data.
        """
        return {'acum_eig': self.acum_eig_, 'num_dims': self.nd_}

    def fit(self, X, y):
        """
        Fit the model from the data in X and the labels in y.

        Parameters
        ----------
        X : array-like, shape (N x d)
            Training vector, where N is the number of samples, and d is the number of features.

        y : array-like, shape (N)
            Labels vector, where N is the number of samples.

        Returns
        -------
        self : object
            Returns the instance itself.
        """
        X, y = check_X_y(X, y)
        self.X_, self.y_ = X, y

        self.n_, self.d_ = X.shape

        het_neighs, hom_neighs = DMLMJ._compute_neighborhoods(X, y, self.n_neighbors)

        if self.num_dims is None:
            num_dims = self.d_
        else:
            num_dims = min(self.num_dims, self.d_)

        S, D = DMLMJ._compute_matrices(X, het_neighs, hom_neighs)

        # Regularization
        Id = np.eye(self.d_)
        if np.abs(np.linalg.det(S) < self.reg_tol):
            S = (1 - self.alpha) * S + self.alpha * Id
        if np.abs(np.linalg.det(D) < self.reg_tol):
            D = (1 - self.alpha) * D + self.alpha * Id

        # Eigenvalues and eigenvectors of S-1D
        self.eig_vals_, self.eig_vecs_ = eigh(D, S)
        # todo divison was commmented, but it's so much better now, and fast!
        vecs_orig = self.eig_vecs_.copy()/np.apply_along_axis(np.linalg.norm, 0, self.eig_vecs_)
        # Reordering
        self.eig_pairs_ = [(np.abs(self.eig_vals_[i]), vecs_orig[:, i]) for i in xrange(self.eig_vals_.size)]
        self.eig_pairs_ = sorted(self.eig_pairs_, key=lambda k: k[0] + 1 / k[0], reverse=True)

        for i, p in enumerate(self.eig_pairs_):
            self.eig_vals_[i] = p[0]
            self.eig_vecs_[i, :] = p[1]

        self.L_ = self.eig_vecs_[:num_dims, :]

        self.nd_ = num_dims
        self.acum_eigvals_ = np.cumsum(self.eig_vals_)
        self.acum_eig_ = self.acum_eigvals_[num_dims - 1] / self.acum_eigvals_[-1]

        return self

    @staticmethod
    def _compute_neighborhoods(X, y, k):
        n, d = X.shape  # n = nr of samples, d = nr of features
        het_neighs = np.empty([n, k], dtype=int)  # k = nr of elements in the neighbourhood
        hom_neighs = np.empty([n, k], dtype=int)
        distance_matrix = pairwise_distances(X=X, n_jobs=-1)
        for i, x in enumerate(X):
            cur_class = y[i]
            mask_het = np.flatnonzero(y != cur_class)
            mask_hom = np.concatenate([np.flatnonzero(y[:i] == cur_class), (i + 1) + np.flatnonzero(y[i + 1:] == cur_class)])

            enemy_dists = [(m, distance_matrix[i, m]) for m in mask_het]
            enemy_dists = sorted(enemy_dists, key=lambda v: v[1])


            friend_dists = [(m, distance_matrix[i, m]) for m in mask_hom]
            friend_dists = sorted(friend_dists, key=lambda v: v[1])
            if len(friend_dists) < k:
                print(friend_dists)

            for j, p in enumerate(enemy_dists[:k]):
                het_neighs[i, j] = p[0]

            for j, p in enumerate(friend_dists[:k]):
                # if p[0] > n:
                # print(p[0])
                hom_neighs[i, j] = p[0]

        return het_neighs, hom_neighs

    @staticmethod
    def _compute_matrices(X, het_neighs, hom_neighs):
        n, d = X.shape
        k = het_neighs.shape[1]
        S = np.zeros([d, d])
        D = np.zeros([d, d])

        for i, x in enumerate(X):
            for j in xrange(k):
                # todo is this a good solution
                if 0 <= hom_neighs[i, j] < n:
                    S += np.outer(x - X[hom_neighs[i, j], :], x - X[hom_neighs[i, j], :])
                if 0 <= het_neighs[i, j] < n:
                    D += np.outer(x - X[het_neighs[i, j], :], x - X[het_neighs[i, j], :])

        dsize = n * k
        S /= dsize
        D /= dsize

        return S, D


class KDMLMJ(KernelDML_Algorithm):
    """
    The kernelized version of DMLMJ.

    Parameters
    ----------
    num_dims : int, default=None
        Dimension desired for the transformed data.

    n_neighbors : int, default=3
        Number of neighbors to consider in the computation of the difference spaces.

    alpha : float, default=0.001
        Regularization parameter for inverse matrix computation.

    reg_tol : float, default=1e-10
        Tolerance threshold for applying regularization. The tolerance is compared with the matrix determinant.

    kernel : "linear" | "poly" | "rbf" | "sigmoid" | "cosine" | "precomputed"
        Kernel. Default="linear".

    gamma : float, default=1/n_features
        Kernel coefficient for rbf, poly and sigmoid kernels. Ignored by other
        kernels.

    degree : int, default=3
        Degree for poly kernels. Ignored by other kernels.

    coef0 : float, default=1
        Independent term in poly and sigmoid kernels.
        Ignored by other kernels.

    kernel_params : mapping of string to any, default=None
        Parameters (keyword arguments) and values for kernel passed as
        callable object. Ignored by other kernels.

    References
    ----------
        Bac Nguyen, Carlos Morell and Bernard De Baets. “Supervised distance metric learning through
        maximization of the Jeffrey divergence”. In: Pattern Recognition 64 (2017), pages 215-225.
    """

    def __init__(self,
                 num_dims=None,
                 n_neighbors=3,
                 alpha=0.001,
                 reg_tol=1e-10,
                 kernel="linear",
                 gamma=None,
                 degree=3,
                 coef0=1,
                 kernel_params=None):
        self.num_dims = num_dims
        self.n_neighbors = n_neighbors
        self.alpha = alpha
        self.reg_tol = reg_tol

        self.kernel = kernel
        self.gamma = gamma
        self.degree = degree
        self.coef0 = coef0
        self.kernel_params = kernel_params

        # Metadata
        self.acum_eig_ = None
        self.nd_ = None

    def transformer(self):
        """
        Obtains the learned projection.

        Returns
        -------
        A : (d'x N) matrix, where d' is the desired output dimension, and N is the number of samples.
            To apply A to a new sample x, A must be multiplied by the kernel vector of dimension N
            obtained by taking the kernels between x and each training sample.
        """
        return self.L_

    def metadata(self):
        """
        Obtains algorithm metadata.

        Returns
        -------
        meta : A dictionary with the following metadata:
            acum_eig : eigenvalue rate accumulated in the learned output respect to the total dimension.

            num_dims : dimension of the reduced data.
        """
        return {'acum_eig': self.acum_eig_, 'num_dims': self.nd_}

    def fit(self, X, y):
        """
        Fit the model from the data in X and the labels in y.

        Parameters
        ----------
        X : array-like, shape (N x d)
            Training vector, where N is the number of samples, and d is the number of features.

        y : array-like, shape (N)
            Labels vector, where N is the number of samples.

        Returns
        -------
        self : object
            Returns the instance itself.
        """
        X, y = check_X_y(X, y)
        self.X_, self.y_ = X, y

        K = self._get_kernel(X)

        self.n_, self.d_ = X.shape

        het_neighs, hom_neighs = DMLMJ._compute_neighborhoods(X, y, self.n_neighbors)

        if self.num_dims is None:
            num_dims = self.d_
        else:
            num_dims = min(self.num_dims, self.d_)

        U, V = DMLMJ._compute_matrices(K, het_neighs, hom_neighs)

        # Regularization
        Id = np.eye(self.n_)
        if np.abs(np.linalg.det(U) < self.reg_tol):
            U = (1 - self.alpha) * U + self.alpha * Id
        if np.abs(np.linalg.det(V) < self.reg_tol):
            V = (1 - self.alpha) * V + self.alpha * Id

        # Eigenvalues and eigenvectors of S-1D
        self.eig_vals_, self.eig_vecs_ = eigh(V, U)
        vecs_orig = self.eig_vecs_.copy()/np.apply_along_axis(np.linalg.norm,0,self.eig_vecs_)
        # Reordering
        self.eig_pairs_ = [(np.abs(self.eig_vals_[i]), vecs_orig[:, i]) for i in xrange(self.eig_vals_.size)]
        self.eig_pairs_ = sorted(self.eig_pairs_, key=lambda k: k[0] + 1 / k[0], reverse=True)

        for i, p in enumerate(self.eig_pairs_):
            self.eig_vals_[i] = p[0]
            self.eig_vecs_[i, :] = p[1]

        self.L_ = self.eig_vecs_[:num_dims, :]

        self.nd_ = num_dims
        self.acum_eigvals_ = np.cumsum(self.eig_vals_)
        self.acum_eig_ = self.acum_eigvals_[num_dims - 1] / self.acum_eigvals_[-1]

        return self

    @staticmethod
    def _compute_neighborhoods(K, X, y, k):
        n, d = X.shape
        het_neighs = np.empty([n, k], dtype=int)
        hom_neighs = np.empty([n, k], dtype=int)
        distance_matrix = pairwise_sq_distances_from_dot(K)
        for i in xrange(n):
            cur_class = y[i]
            mask_het = np.flatnonzero(y != cur_class)
            mask_hom = np.concatenate([np.flatnonzero(y[:i] == cur_class),
                                       (i + 1) + np.flatnonzero(y[i + 1:] == cur_class)])

            enemy_dists = [(m, distance_matrix[i, m]) for m in mask_het]
            enemy_dists = sorted(enemy_dists, key=lambda v: v[1])

            friend_dists = [(m, distance_matrix[i, m]) for m in mask_hom]
            friend_dists = sorted(friend_dists, key=lambda v: v[1])

            for j, p in enumerate(enemy_dists[:k]):
                het_neighs[i, j] = p[0]

            for j, p in enumerate(friend_dists[:k]):
                hom_neighs[i, j] = p[0]

        return het_neighs, hom_neighs

    @staticmethod
    def _compute_matrices(K, het_neighs, hom_neighs):
        k = het_neighs.shape[1]
        n, _ = K.shape
        U = np.zeros([n, n])
        V = np.zeros([n, n])

        for i, k in enumerate(K):
            for j in xrange(k):
                U += np.outer(k - K[hom_neighs[i, j], :], k - K[hom_neighs[i, j], :])
                V += np.outer(k - K[het_neighs[i, j], :], k - K[het_neighs[i, j], :])

        dsize = n * k

        U /= dsize
        V /= dsize

        return U, V
