package com.firewatch.api;

/** Loi tra ve cho frontend dang {"error": "..."} (xem ApiErrorHandler). */
public class ApiError extends RuntimeException {
    public final int status;

    public ApiError(int status, String message) {
        super(message);
        this.status = status;
    }
}
