# -*- coding: utf-8 -*-
import mne
import pandas as pd
import numpy as np


# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
def cvxEDA(y, delta, tau0=2., tau1=0.7, delta_knot=10., alpha=0.4, gamma=1e-2,
           solver=None, options={'reltol':1e-9}):
    """
    CVXEDA Convex optimization approach to electrodermal activity processing

    This function implements the cvxEDA algorithm described in "cvxEDA: a
    Convex Optimization Approach to Electrodermal Activity Processing"
    (http://dx.doi.org/10.1109/TBME.2015.2474131, also available from the
    authors' homepages).

    Parameters
    ----------
       y
           observed EDA signal (we recommend normalizing it: y = zscore(y))
       delta
           sampling interval (in seconds) of y
       tau0
           slow time constant of the Bateman function
       tau1
           fast time constant of the Bateman function
       delta_knot
           time between knots of the tonic spline function
       alpha
           penalization for the sparse SMNA driver
       gamma
           penalization for the tonic spline coefficients
       solver
           sparse QP solver to be used, see cvxopt.solvers.qp
       options
           solver options, see http://cvxopt.org/userguide/coneprog.html#algorithm-parameters

    Returns
    ----------
       r
           phasic component
       p
           sparse SMNA driver of phasic component
       t
           tonic component
       l
           coefficients of tonic spline
       d
           offset and slope of the linear drift term
       e
           model residuals
       obj
           value of objective function being minimized (eq 15 of paper)

    Authors
    ----------
    Luca Citi (lciti@ieee.org), Alberto Greco

    Citation
    ----------
    A Greco, G Valenza, A Lanata, EP Scilingo, and L Citi
    "cvxEDA: a Convex Optimization Approach to Electrodermal Activity Processing"
    IEEE Transactions on Biomedical Engineering, 2015
    DOI: 10.1109/TBME.2015.2474131

    Dependencies
    ----------
    - cvxopt
    - numpy
    """
    import cvxopt as cv
    import cvxopt.solvers

    n = len(y)
    y = cv.matrix(y)

    # bateman ARMA model
    a1 = 1./min(tau1, tau0) # a1 > a0
    a0 = 1./max(tau1, tau0)
    ar = np.array([(a1*delta + 2.) * (a0*delta + 2.), 2.*a1*a0*delta**2 - 8.,
        (a1*delta - 2.) * (a0*delta - 2.)]) / ((a1 - a0) * delta**2)
    ma = np.array([1., 2., 1.])

    # matrices for ARMA model
    i = np.arange(2, n)
    A = cv.spmatrix(np.tile(ar, (n-2,1)), np.c_[i,i,i], np.c_[i,i-1,i-2], (n,n))
    M = cv.spmatrix(np.tile(ma, (n-2,1)), np.c_[i,i,i], np.c_[i,i-1,i-2], (n,n))

    # spline
    delta_knot_s = int(round(delta_knot / delta))
    spl = np.r_[np.arange(1.,delta_knot_s), np.arange(delta_knot_s, 0., -1.)] # order 1
    spl = np.convolve(spl, spl, 'full')
    spl /= max(spl)
    # matrix of spline regressors
    i = np.c_[np.arange(-(len(spl)//2), (len(spl)+1)//2)] + np.r_[np.arange(0, n, delta_knot_s)]
    nB = i.shape[1]
    j = np.tile(np.arange(nB), (len(spl),1))
    p = np.tile(spl, (nB,1)).T
    valid = (i >= 0) & (i < n)
    B = cv.spmatrix(p[valid], i[valid], j[valid])

    # trend
    C = cv.matrix(np.c_[np.ones(n), np.arange(1., n+1.)/n])
    nC = C.size[1]

    # Solve the problem:
    # .5*(M*q + B*l + C*d - y)^2 + alpha*sum(A,1)*p + .5*gamma*l'*l
    # s.t. A*q >= 0

    old_options = cv.solvers.options.copy()
    cv.solvers.options.clear()
    cv.solvers.options.update(options)
    if solver == 'conelp':
        # Use conelp
        z = lambda m,n: cv.spmatrix([],[],[],(m,n))
        G = cv.sparse([[-A,z(2,n),M,z(nB+2,n)],[z(n+2,nC),C,z(nB+2,nC)],
                    [z(n,1),-1,1,z(n+nB+2,1)],[z(2*n+2,1),-1,1,z(nB,1)],
                    [z(n+2,nB),B,z(2,nB),cv.spmatrix(1.0, range(nB), range(nB))]])
        h = cv.matrix([z(n,1),.5,.5,y,.5,.5,z(nB,1)])
        c = cv.matrix([(cv.matrix(alpha, (1,n)) * A).T,z(nC,1),1,gamma,z(nB,1)])
        res = cv.solvers.conelp(c, G, h, dims={'l':n,'q':[n+2,nB+2],'s':[]})
        obj = res['primal objective']
    else:
        # Use qp
        Mt, Ct, Bt = M.T, C.T, B.T
        H = cv.sparse([[Mt*M, Ct*M, Bt*M], [Mt*C, Ct*C, Bt*C],
                    [Mt*B, Ct*B, Bt*B+gamma*cv.spmatrix(1.0, range(nB), range(nB))]])
        f = cv.matrix([(cv.matrix(alpha, (1,n)) * A).T - Mt*y,  -(Ct*y), -(Bt*y)])
        res = cv.solvers.qp(H, f, cv.spmatrix(-A.V, A.I, A.J, (n,len(f))),
                            cv.matrix(0., (n,1)), solver=solver)
        obj = res['primal objective'] + .5 * (y.T * y)
    cv.solvers.options.clear()
    cv.solvers.options.update(old_options)

    l = res['x'][-nB:]
    d = res['x'][n:n+nC]
    t = B*l + C*d
    q = res['x'][:n]
    p = A * q
    r = M * q
    e = y - r - t

    return(np.array(a).ravel() for a in (r, p, t, l, d, e, obj))


# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
def extract_peak(channel_data, value="max", size=0):
    """
    Exctract the peak (max or min) of one or several channels.

    Parameters
    ----------
    channel_data = pandas.DataFrame
        Use the `to_data_frame()` method for evoked nme data.
    value = str
        "max" or "min".
    size = int
        Return an averaged peak from how many points before and after.

    Returns
    ----------
    tuple
        (peak, time_peak)

    Example
    ----------
    >>> import neuropsydia as n
    >>> n.start(False)
    >>>
    >>> channel_data = evoked.pick_channels(["C1", "C2"]).to_data_frame()
    >>> peak, time_peak = extract_peak(channel_data, size=2)
    >>>
    >>> n.close()

    Authors
    ----------
    Dominique Makowski

    Dependencies
    ----------
    - mne > 0.13.0
    - numpy
    - pandas
    """
    data = channel_data.mean(axis=1)
    data.plot()
    if value == "max":
        peak = np.max(data)
        time_peak = np.argmax(data)
    if value == "min":
        peak = np.min(data)
        time_peak = np.argmin(data)
    if size > 0:
        peak_list = [peak]
        peak_index = list(data.index).index(time_peak)
        data = data.reset_index(drop=True)
        for i in range(size):
            peak_list.append(data[peak_index+int(i+1)])
            peak_list.append(data[peak_index-int(i-1)])
        peak = np.mean(peak_list)
    return(peak, time_peak)




# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
# ==============================================================================
def triggers_from_photodiode(photo_channel, names=None, treshold=0.04):
    """
    Create MNE compatible triggers based on a photodiode channel.

    Parameters
    ----------
    photo_channel = MNE channel
        The photodiode channel.
    names = list
        A list of event names.
    treshold = float
        The treshold to select the triggers.

    Returns
    ----------
    tuple
        (events, event_id)

    Example
    ----------
    >>> import neuropsydia as n
    >>> n.start(False)
    >>>
    >>> raw = mne.io.read_raw("eeg_file")
    >>> photo_channel = raw.copy().pick_channels(['PHOTO'])
    >>> events, event_id = triggers_from_photodiode(photo_channel)
    >>> raw.add_events(events, stim_channel="STI 014")
    >>>
    >>> n.close()

    Authors
    ----------
    Dominique Makowski

    Dependencies
    ----------
    - mne > 0.13.0
    - numpy
    """
    original_names = names.copy()

    if names != None:
        event_names = list(set(names))
        event_index = [1, 2, 3, 4, 5, 32]
        event_id = {}
        for i in enumerate(event_names):
            names = [event_index[i[0]] if x==i[1] else x for x in names]
            event_id[i[1]] = event_index[i[0]]

    # Extract data from one channel
    data, times = photo_channel[:]
    T = list(data.T)

    events = []
    for i in range(len(times)):
        if T[i] < treshold:
            events.append(1)
        else:
            events.append(0)

    event_times = []
    for i in range(len(events)):
        if i > 0:
            if events[i]==1 and events[i-1]==0:
                event_times.append(i)

    if len(event_times) != len(original_names):
        print("NEUROPSYDIA ERROR: triggers_from_photodiode(): length of trigger names vector does not match the number of detected triggers (n = " +
              str(len(event_times)) + "), change names or crop the raw data")
    if names != None:
        events = np.array([event_times, [0]*len(event_times), names]).T
    else:
        events = np.array([event_times, [0]*len(event_times), [1]*len(event_times)]).T

    return(events, event_id)



