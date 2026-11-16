package com.firewatch.api;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import java.util.Map;

/** Bat loi chung cho moi controller trong goi api. */
@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(ApiError.class)
    ResponseEntity<Map<String, String>> onApiError(ApiError e) {
        return ResponseEntity.status(e.status).body(Map.of("error", e.getMessage()));
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class, ClassCastException.class})
    ResponseEntity<Map<String, String>> onBadInput() {
        return ResponseEntity.badRequest().body(Map.of("error", "Dữ liệu không hợp lệ."));
    }
}
