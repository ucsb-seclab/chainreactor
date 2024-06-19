; in this scenario, writer can be used to inject shellcode in sensitive_script
; writer is a user binary (a custom script, for example) and not a system binary
; when an executable is custom, we assume it does not drop the privileges on execution
(define (problem escalate-shell-user-exec)
  (:domain micronix)
  (:objects
    alice bob - user
    sensitive_script - executable
    g1 g2 - group
    directory - directory
    writer - executable
    process - process
    data - data
    location - local
  )

  (:init
    (CAP_write_file writer)
    (user_executable writer)
    (suid_executable writer)
    (file_owner writer alice g1)

    (user_group alice g1)
    (user_group bob g2)

    (file_owner sensitive_script alice g1)
    (file_present_at_location sensitive_script location)
    (file_contents sensitive_script data)
    (executable_systematically_called_by sensitive_script alice)
    (user_file_permission bob sensitive_script FS_EXEC)
    (user_file_permission bob writer FS_EXEC)    
    
    (controlled_user bob)
  )

  (:goal (controlled_user alice))
)