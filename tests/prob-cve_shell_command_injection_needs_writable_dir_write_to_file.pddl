(define (problem cve_shell_command_injection_needs_writable_dir)
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

    (CAP_cve_shell_command_injection_needs_writable_directory cve_vulnerable_executable directory)
    (system_executable cve_vulnerable_executable)
    (user_directory_permission directory user FS_WRITE)
    (file_owner file user group)
    (user_group user group)
    (user_data_in_buffer user data)
    (controlled_user user)

  )

  (:goal (file_contents file data))
)