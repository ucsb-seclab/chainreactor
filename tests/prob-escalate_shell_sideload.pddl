(define (problem escalate-shell)
  (:domain micronix)
  (:objects
    alice bob - user
    alice_group bob_group - group
    directory - directory
    writer bash - executable
    library - file
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
    
    (file_owner library alice alice_group)
    (file_present_at_location library location)
    (executable_always_loads_file bash library)
    
    (executable_systematically_called_by bash alice)
    (user_file_permission bob library FS_WRITE)
    
    (controlled_user bob)
  )

  (:goal (controlled_user alice))
)