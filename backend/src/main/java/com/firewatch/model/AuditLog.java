package com.firewatch.model;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "audit_logs")
public class AuditLog {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long id;
    public Instant occurredAt = Instant.now();
    public String actor;                // luu ten dang nhap dang text (khong FK)
    public String action;
    public String target;
}
