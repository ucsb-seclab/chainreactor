(define (problem cve_shell_command_injection)
  (:domain micronix)
  (:objects
    cve_vulnerable_executable - executable
    user - user
    file - file
    group - group
    directory - directory
    process - process
    data - data
    location - local
  )

  (:init
 ; Precondition

    (CAP_cve_shell_command_injection cve_vulnerable_executable)
    (system_executable cve_vulnerable_executable)
    (file_owner file user group)
    (user_group user group)
    (user_data_in_buffer user data)
    (controlled_user user)

  )

  (:goal (file_contents file data))
)