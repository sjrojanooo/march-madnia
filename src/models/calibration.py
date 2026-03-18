"""Probability calibration techniques for improving model confidence estimates.

Implements temperature scaling and isotonic regression for post-hoc calibration
of miscalibrated classifiers.
"""

import logging

import numpy as np
from sklearn.isotonic import IsotonicRegression
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


class TemperatureScaling:
    """Temperature scaling for probability calibration.

    Divides model logits by a learned temperature parameter T before applying
    sigmoid. Temperature > 1 increases uncertainty (flattens probabilities),
    T < 1 increases confidence. Optimized to minimize NLL on a calibration set.

    Reference: Guo et al. "On Calibration of Modern Neural Networks" (ICML 2017)
    """

    def __init__(self):
        self.temperature = 1.0
        self.fitted = False

    def fit(self, y_proba: np.ndarray, y_true: np.ndarray) -> "TemperatureScaling":
        """Fit temperature parameter on calibration data.

        Args:
            y_proba: Predicted probabilities (already in [0, 1] range).
            y_true: True binary labels.

        Returns:
            self
        """
        if len(np.unique(y_true)) < 2:
            logger.warning("Only one class in calibration set; skipping temperature scaling")
            self.fitted = True
            return self

        # Convert probabilities to logits (avoid inf by clipping)
        y_proba = np.clip(y_proba, 1e-15, 1 - 1e-15)
        logits = np.log(y_proba / (1 - y_proba))

        def nll(t):
            """Negative log likelihood with temperature scaling."""
            t = t[0]
            if t <= 0.01 or t > 100:
                return 1e10
            scaled_logits = logits / t
            # Clip logits to avoid overflow
            scaled_logits = np.clip(scaled_logits, -500, 500)
            # Sigmoid
            probs = 1 / (1 + np.exp(-scaled_logits))
            probs = np.clip(probs, 1e-15, 1 - 1e-15)
            return -np.mean(y_true * np.log(probs) + (1 - y_true) * np.log(1 - probs))

        # Optimize temperature with bounds
        # Reasonable range: 0.5 to 5.0 (lower = more confident, higher = less confident)
        result = minimize(
            nll,
            x0=[1.0],
            method="L-BFGS-B",
            bounds=[(0.5, 5.0)],
            options={"maxiter": 1000},
        )
        self.temperature = float(result.x[0])
        self.fitted = True

        logger.info("Temperature scaling fitted: T=%.4f", self.temperature)
        return self

    def calibrate(self, y_proba: np.ndarray) -> np.ndarray:
        """Apply temperature scaling to probabilities.

        Args:
            y_proba: Predicted probabilities in [0, 1].

        Returns:
            Calibrated probabilities in [0, 1].
        """
        if not self.fitted:
            logger.warning("TemperatureScaling not fitted; returning original probabilities")
            return y_proba

        y_proba = np.clip(y_proba, 1e-15, 1 - 1e-15)
        logits = np.log(y_proba / (1 - y_proba))
        scaled_logits = logits / self.temperature
        calibrated = 1 / (1 + np.exp(-scaled_logits))
        return np.clip(calibrated, 0, 1)


class IsotonicRegressionCalibrator:
    """Isotonic regression for probability calibration.

    Fits a monotonic mapping from predicted probabilities to empirical
    frequencies on a calibration set. More flexible than temperature scaling
    but requires more data and can overfit with small calibration sets.
    """

    def __init__(self):
        self.calibrator = IsotonicRegression(out_of_bounds="clip")
        self.fitted = False

    def fit(self, y_proba: np.ndarray, y_true: np.ndarray) -> "IsotonicRegressionCalibrator":
        """Fit isotonic regression on calibration data.

        Args:
            y_proba: Predicted probabilities.
            y_true: True binary labels.

        Returns:
            self
        """
        if len(np.unique(y_true)) < 2:
            logger.warning("Only one class in calibration set; skipping isotonic calibration")
            self.fitted = True
            return self

        if len(y_proba) < 10:
            logger.warning(
                "Very small calibration set (%d samples); isotonic regression may overfit",
                len(y_proba),
            )

        self.calibrator.fit(y_proba, y_true)
        self.fitted = True

        logger.info("Isotonic regression fitted on %d samples", len(y_proba))
        return self

    def calibrate(self, y_proba: np.ndarray) -> np.ndarray:
        """Apply isotonic regression to probabilities.

        Args:
            y_proba: Predicted probabilities.

        Returns:
            Calibrated probabilities.
        """
        if not self.fitted:
            logger.warning("IsotonicRegressionCalibrator not fitted; returning original")
            return y_proba

        return self.calibrator.predict(y_proba)


def calibrate_ensemble_predictions(
    model,
    X_calib,
    y_calib,
    X_test,
    method: str = "temperature",
):
    """Calibrate ensemble predictions using a calibration set.

    Args:
        model: Fitted ensemble model with predict_proba method.
        X_calib: Calibration set features.
        y_calib: Calibration set labels.
        X_test: Test set features.
        method: "temperature" or "isotonic".

    Returns:
        Tuple of (y_proba_calibrated, calibrator_object)
    """
    logger.info("Calibrating predictions using %s method on %d samples", method, len(X_calib))

    # Get raw predictions
    y_proba_calib = model.predict_proba(X_calib)[:, 1]
    y_proba_test = model.predict_proba(X_test)[:, 1]

    if method == "temperature":
        calibrator = TemperatureScaling()
    elif method == "isotonic":
        calibrator = IsotonicRegressionCalibrator()
    else:
        raise ValueError(f"Unknown calibration method: {method}")

    calibrator.fit(y_proba_calib, y_calib)
    y_proba_calibrated = calibrator.calibrate(y_proba_test)

    return y_proba_calibrated, calibrator
