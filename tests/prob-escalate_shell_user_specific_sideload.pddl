(define (problem escalate-shell)
  (:domain micronix)
  (:objects
    alice bob - user
    alice_group bob_group - group
    directory - directory
    writer bash - executable
    bashrc - file
    process - process
    data - data
    location - local
  )

  (:init
    (CAP_write_file writer)
    (system_executable writer)
    (CAP_shell bash)
    (system_executable bash)

    (user_group alice alice_group)
    (user_group bob bob_group)
    
    (file_owner bashrc alice alice_group)
    (file_present_at_location bashrc location)
    (executable_loads_user_specific_file bash alice bashrc)
    
    (executable_systematically_called_by bash alice)
    (user_file_permission bob bashrc FS_WRITE)
    
    (controlled_user bob)
  )

  (:goal (controlled_user alice))
)