import numpy as np
from joblib import Parallel, delayed
import pandas
from itertools import product
from libsvmdata.datasets import fetch_libsvm
from celer import LogisticRegression

from sparse_ho.ho_dirty import (
    grad_search, grad_search_backtracking_cd_dirty2, grad_search_scipy)
from sparse_ho.implicit_forward import ImplicitForward
from sparse_ho.utils_datasets import clean_dataset, get_alpha_max
from sparse_ho.utils import Monitor
from sparse_ho.criterion import LogisticMulticlass
from sparse_ho.hyperopt_wrapper import hyperopt_wrapper


dataset_names = ["rcv1_multiclass"]
# dataset_names = ["mnist", "usps", "sector_scale"]
# dataset_names = ["news20_multiclass"]
# dataset_names = ["sector_scale"]
# dataset_names = ["aloi"]
# dataset_names = ["sector_scale", "aloi"]

# methods = ['implicit_forward_scipy']
# methods = ['grid_search']
# methods = ["implicit_forward", "random", "bayesian"]
methods = ["random", "bayesian"]
# methods = ["bayesian"]
# methods = ["implicit_forward_cdls"]
# methods = ["implicit_forward"]
# methods = ["implicit_forward_cdls", "implicit_forward"]
# methods = ["implicit_forward", "random", "bayesian"]

tols = 1e-7
n_outers = [40]

dict_t_max = {}
dict_t_max["rcv1_multiclass"] = 3600
dict_t_max["real-sim"] = 100
dict_t_max["leukemia"] = 10
dict_t_max["20news"] = 500
dict_t_max["usps"] = 1500
dict_t_max["sensit"] = 3600
dict_t_max["aloi"] = 3600
dict_t_max["sector_scale"] = 3600
dict_t_max["news20_multiclass"] = 3600
dict_t_max["mnist"] = 1200


dict_subsampling = {}
dict_subsampling["mnist"] = (5_000, 1000)
dict_subsampling["rcv1_multiclass"] = (21_000, 20_000)
dict_subsampling["aloi"] = (5_000, 100)
dict_subsampling["aloi"] = (5_000, 100)
dict_subsampling["usps"] = (10_000, 10_000)
dict_subsampling["sensit"] = (100_000, 100)
dict_subsampling["sector_scale"] = (10_000, 30_000)
dict_subsampling["news20_multiclass"] = (10_000, 30_000)

dict_max_eval = {}
dict_max_eval["mnist"] = 50
dict_max_eval["rcv1_multiclass"] = 100
dict_max_eval["aloi"] = 50
dict_max_eval["usps"] = 40
dict_max_eval["sensit"] = 40
dict_max_eval["sector_scale"] = 40
dict_max_eval["news20_multiclass"] = 40


def parallel_function(
        dataset_name, method, tol=1e-8, n_outer=15):

    # load data
    X, y = fetch_libsvm(dataset_name)
    # subsample the samples and the features
    # n_samples = 100
    # n_features = 100
    # n_samples = 5_000
    # n_features = 1_000
    n_samples, n_features = dict_subsampling[dataset_name]
    t_max = dict_t_max[dataset_name]
    # t_max = 3600

    X, y = clean_dataset(X, y, n_samples, n_features)
    alpha_max, n_classes = get_alpha_max(X, y)
    log_alpha_max = np.log(alpha_max)  # maybe to change alpha max value

    algo = ImplicitForward(None, n_iter_jac=2000)
    estimator = LogisticRegression(
        C=1, fit_intercept=False, warm_start=True, max_iter=30, verbose=False)
    logit_multiclass = LogisticMulticlass(X, y, algo, estimator)
    monitor = Monitor()
    if method == "implicit_forward":
        log_alpha0 = np.ones(n_classes) * np.log(0.1 * alpha_max)
        grad_search(
            logit_multiclass, log_alpha0, monitor, n_outer=n_outer, tol=tol,
            t_max=t_max)
    elif method == "implicit_forward_cdls":
        log_alpha0 = np.ones(n_classes) * np.log(0.01 * alpha_max)
        grad_search_backtracking_cd_dirty2(
            logit_multiclass, log_alpha0, monitor, n_outer=n_outer, tol=tol,
            maxit_ln=10, t_max=t_max)
    elif method == "implicit_forward_scipy":
        log_alpha0 = np.ones(n_classes) * np.log(0.1 * alpha_max)
        grad_search_scipy(
            logit_multiclass, log_alpha0, monitor, n_outer=n_outer, tol=tol,
            t_max=t_max)
    # if method == "brent_cd":
    #     log_alpha0 = np.ones(n_classes) * np.log(0.1 * alpha_max)
    #     brent_cd(
    #         logit_multiclass, log_alpha0, monitor, n_outer=10, tol=tol,
    #         t_max=t_max)
    elif method.startswith(('random', 'bayesian')):
        max_evals = dict_max_eval[dataset_name]
        log_alpha_min = np.log(alpha_max) - 7
        hyperopt_wrapper(
            logit_multiclass, log_alpha_min, log_alpha_max, monitor,
            max_evals=max_evals, tol=tol, t_max=t_max, method=method,
            size_space=n_classes)
    elif method == 'grid_search':
        n_alphas = 20
        p_alphas = np.geomspace(1, 0.001, n_alphas)
        p_alphas = np.tile(p_alphas, (n_classes, 1))
        for i in range(n_alphas):
            logit_multiclass.get_val_grad(
                np.log(alpha_max * p_alphas[:, i]), monitor)
            print("%i / %i  || crosss entropy %f  || accuracy val %f  || accuracy test %f" % (
                i, n_alphas, monitor.objs[-1], monitor.acc_vals[-1], monitor.acc_tests[-1]))

    monitor.times = np.array(monitor.times).copy()
    monitor.objs = np.array(monitor.objs).copy()
    monitor.acc_vals = np.array(monitor.acc_vals).copy()
    monitor.acc_tests = np.array(monitor.acc_tests).copy()
    monitor.log_alphas = np.array(monitor.log_alphas).copy()
    return (
        dataset_name, method, tol, n_outer, monitor.times, monitor.objs,
        monitor.acc_vals, monitor.acc_tests, monitor.log_alphas, log_alpha_max,
        n_samples, n_features, n_classes)


print("enter parallel")
backend = 'loky'
# n_jobs = 1
n_jobs = len(methods) * len(dataset_names)
results = Parallel(n_jobs=n_jobs, verbose=100, backend=backend)(
    delayed(parallel_function)(
        dataset_name, method, n_outer=n_outer, tol=tols)
    for dataset_name, method, n_outer in product(
        dataset_names, methods, n_outers))
print('OK finished parallel')

df = pandas.DataFrame(results)
df.columns = [
    'dataset', 'method', 'tol', 'n_outer', 'times', 'objs', 'acc_vals',
    'acc_tests', 'log_alphas', "log_alpha_max",
    "n_subsamples", "n_subfeatures", "n_classes"]

for dataset_name in dataset_names:
    for method in methods:
        df[(df['dataset'] == dataset_name) & (df['method'] == method)].to_pickle(
            "results/%s_%s.pkl" % (dataset_name, method))